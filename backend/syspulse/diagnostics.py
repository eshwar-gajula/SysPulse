"""Small, explainable rules that never take action on the user's system."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from math import ceil
from statistics import median

from .models import DiagnosticFinding, ProcessInfo, SystemSnapshot

CPU_THRESHOLD = 85.0
CPU_SUSTAINED_SECONDS = 60.0
MEMORY_GROWTH_WINDOW_SECONDS = 300.0
MEMORY_GROWTH_MIN_SECONDS = 120.0
MEMORY_GROWTH_MIN_BYTES = 128 * 1024**2
MEMORY_GROWTH_MIN_RATIO = 0.25


def _epoch(timestamp: str) -> float:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(UTC).timestamp()


def _finding(
    *,
    identifier: str,
    severity: str,
    title: str,
    observation: str,
    possible_cause: str,
    evidence: list[str],
    recommendation: str,
    timestamp: str,
) -> DiagnosticFinding:
    return DiagnosticFinding(
        id=identifier,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        observation=observation,
        possible_cause=possible_cause,
        evidence=evidence,
        recommendation=recommendation,
        observed_at=timestamp,
    )


def _process_memory_growth(
    history: Sequence[SystemSnapshot],
    sample_interval_seconds: float,
) -> list[DiagnosticFinding]:
    current = history[-1]
    cutoff = _epoch(current.timestamp) - MEMORY_GROWTH_WINDOW_SECONDS
    minimum_samples = max(3, min(10, ceil(MEMORY_GROWTH_MIN_SECONDS / max(1.0, sample_interval_seconds))))
    candidates: list[tuple[int, float, ProcessInfo, int, int, int, float]] = []

    for process in current.processes:
        observations = [
            (sample.timestamp, matching.memory_bytes)
            for sample in history
            if _epoch(sample.timestamp) >= cutoff
            for matching in sample.processes
            if matching.pid == process.pid and matching.created_at == process.created_at
        ]
        if len(observations) < minimum_samples:
            continue

        duration = _epoch(observations[-1][0]) - _epoch(observations[0][0])
        if duration < MEMORY_GROWTH_MIN_SECONDS:
            continue

        window_size = min(5, max(2, len(observations) // 3))
        baseline = int(median(value for _, value in observations[:window_size]))
        recent = int(median(value for _, value in observations[-window_size:]))
        increase = recent - baseline
        ratio = increase / max(1, baseline)
        if increase >= MEMORY_GROWTH_MIN_BYTES and ratio >= MEMORY_GROWTH_MIN_RATIO:
            candidates.append((increase, ratio, process, baseline, recent, len(observations), duration))

    findings: list[DiagnosticFinding] = []
    for increase, ratio, process, baseline, recent, sample_count, duration in sorted(
        candidates, key=lambda item: item[0], reverse=True
    )[:3]:
        created_epoch = int(_epoch(process.created_at))
        findings.append(
            _finding(
                identifier=f"process.memory-growth.{process.pid}.{created_epoch}",
                severity="warning",
                title=f"Sustained memory growth: {process.name[:100]}",
                observation=(
                    f"{process.name} (PID {process.pid}) RSS increased by "
                    f"{increase / (1024**2):.1f} MiB over {int(duration)} seconds."
                ),
                possible_cause=(
                    "This process has shown sustained resident-memory growth. A leak is one possible explanation, "
                    "but caches, workload changes, and expected application growth can produce similar readings."
                ),
                evidence=[
                    f"Median RSS rose from {baseline / (1024**2):.1f} MiB to {recent / (1024**2):.1f} MiB.",
                    f"Growth is {ratio * 100:.1f}% across {sample_count} observations.",
                ],
                recommendation=(
                    "Compare this process across a longer interval and check expected workload and allocation "
                    "logs before concluding that it has a memory leak."
                ),
                timestamp=current.timestamp,
            )
        )
    return findings


def analyze(
    history: Sequence[SystemSnapshot], sample_interval_seconds: float = 2.0
) -> list[DiagnosticFinding]:
    """Return current findings, requiring sustained evidence before CPU alerts."""
    if not history:
        return []

    current = history[-1]
    metrics = current.metrics
    findings: list[DiagnosticFinding] = []
    timestamp = current.timestamp
    findings.extend(_process_memory_growth(history, sample_interval_seconds))

    cpu_points: list[SystemSnapshot] = []
    for sample in reversed(history):
        cpu = sample.metrics.cpu_percent
        if cpu is None or cpu < CPU_THRESHOLD:
            break
        cpu_points.append(sample)
    cpu_points.reverse()

    if len(cpu_points) >= 2 and _epoch(timestamp) - _epoch(cpu_points[0].timestamp) >= CPU_SUSTAINED_SECONDS:
        average = sum(point.metrics.cpu_percent or 0 for point in cpu_points) / len(cpu_points)
        evidence = [
            f"System CPU stayed at or above {CPU_THRESHOLD:.0f}% for {int(_epoch(timestamp) - _epoch(cpu_points[0].timestamp))} seconds.",
            f"The current 5-sample CPU moving average is {metrics.cpu_average if metrics.cpu_average is not None else average:.1f}%.",
        ]
        heavy = next(
            (
                process
                for process in current.processes
                if process.cpu_percent is not None and process.cpu_percent >= 10.0
            ),
            None,
        )
        cause = "Sustained system-wide CPU work may come from one or more busy processes, background jobs, or kernel activity."
        if heavy is not None:
            evidence.append(
                f"{heavy.name} (PID {heavy.pid}) used {heavy.cpu_percent:.1f}% of total CPU capacity in the latest sample."
            )
            cause = f"{heavy.name} (PID {heavy.pid}) may be contributing to the sustained load; the correlation is not proof of root cause."
        findings.append(
            _finding(
                identifier="cpu.sustained-high",
                severity="warning",
                title="Sustained high CPU",
                observation=f"CPU remained above {CPU_THRESHOLD:.0f}% for at least 60 seconds (smoothed average {average:.1f}%).",
                possible_cause=cause,
                evidence=evidence,
                recommendation="Review the busiest process and its workload and logs. Compare the load with expected activity before changing or stopping anything.",
                timestamp=timestamp,
            )
        )

    memory_percent = metrics.memory_percent
    swap_out = metrics.swap_out_bytes_per_second or 0.0
    if memory_percent is not None and memory_percent >= 95.0:
        pressure = (
            metrics.memory_available_bytes is not None
            and metrics.memory_total_bytes is not None
            and metrics.memory_available_bytes / max(1, metrics.memory_total_bytes) <= 0.05
        )
        if pressure or swap_out > 0:
            severity = "critical" if memory_percent >= 98.0 and pressure else "warning"
            title = "Memory pressure detected"
            observation = f"Memory use is {memory_percent:.1f}% with limited headroom or active swap-out."
            evidence = [f"Memory utilization is {memory_percent:.1f}%."]
            if metrics.memory_available_bytes is not None:
                evidence.append(f"Available memory is {metrics.memory_available_bytes / (1024**3):.2f} GiB.")
            if swap_out > 0:
                evidence.append(f"Swap-out activity is {swap_out / (1024**2):.2f} MiB/s.")
            cause = "The workload may exceed currently available physical memory; this snapshot does not establish a memory leak."
            recommendation = "Check the processes using the most memory and review swap activity and application logs. Look for growth across multiple samples before investigating a leak."
        else:
            severity = "info"
            title = "High memory use"
            observation = (
                f"Memory use is {memory_percent:.1f}%; this reading alone does not establish memory pressure."
            )
            evidence = [f"Memory utilization is {memory_percent:.1f}%."]
            cause = "Applications or the operating system may be using memory that remains reclaimable."
            recommendation = "Review available memory and swap activity. High memory use on its own is not evidence of a memory leak."
        memory_process = max(current.processes, key=lambda item: item.memory_bytes, default=None)
        if memory_process is not None:
            evidence.append(
                f"Largest listed process: {memory_process.name} (PID {memory_process.pid}), {memory_process.memory_bytes / (1024**2):.1f} MiB."
            )
        findings.append(
            _finding(
                identifier="memory.high-use",
                severity=severity,
                title=title,
                observation=observation,
                possible_cause=cause,
                evidence=evidence,
                recommendation=recommendation,
                timestamp=timestamp,
            )
        )

    disk_percent = metrics.disk_percent
    if disk_percent is not None and disk_percent >= 90.0:
        severity = "critical" if disk_percent >= 97.0 else "warning"
        free = metrics.disk_free_bytes
        evidence = [f"The monitored filesystem is {disk_percent:.1f}% full."]
        if free is not None:
            evidence.append(f"Free space is {free / (1024**3):.2f} GiB.")
        findings.append(
            _finding(
                identifier="disk.low-space",
                severity=severity,
                title="Low disk headroom",
                observation=f"The monitored root filesystem is {disk_percent:.1f}% full.",
                possible_cause="Large files, logs, caches, or normal workload growth may be using the remaining space.",
                evidence=evidence,
                recommendation="Check which directories are using space and review log retention before removing files.",
                timestamp=timestamp,
            )
        )

    if (metrics.network_errors_delta or 0) > 0 or (metrics.network_drops_delta or 0) > 0:
        errors = metrics.network_errors_delta or 0
        drops = metrics.network_drops_delta or 0
        evidence = [
            f"The latest sample interval recorded {errors} new network error(s) and {drops} new packet drop(s)."
        ]
        findings.append(
            _finding(
                identifier="network.errors-or-drops",
                severity="warning",
                title="Network interface errors or drops",
                observation=f"Detected {errors} new error(s) and {drops} new drop(s) since the prior sample.",
                possible_cause="A link, driver, interface queue, or remote congestion may be contributing; counters alone do not identify the cause.",
                evidence=evidence,
                recommendation="Check the affected interface counters and system logs with your normal network diagnostic tools.",
                timestamp=timestamp,
            )
        )

    return findings
