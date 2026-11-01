"""Read-only, permission-tolerant system metric and process collection."""

from __future__ import annotations

import math
import os
import platform
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import psutil

from .models import Metrics, MonitorUsage, ProcessInfo, SystemSnapshot

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_PROCESS_LIMIT = 10


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _delta(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None:
        return None
    value = float(current) - float(previous)
    return value if math.isfinite(value) and value >= 0 else None


def _rate(current: float | int | None, previous: float | int | None, seconds: float | None) -> float | None:
    if seconds is None or seconds <= 0:
        return None
    value = _delta(current, previous)
    return value / seconds if value is not None else None


def _counter_sum(counter: Any) -> float:
    """Sum CPU counters without double-counting Linux guest fields."""
    ignored = {"guest", "guest_nice"}
    values = [
        float(value) for name, value in zip(counter._fields, counter, strict=True) if name not in ignored
    ]
    return sum(value for value in values if math.isfinite(value) and value >= 0)


def _counter_busy(counter: Any) -> float:
    excluded = {"idle", "iowait", "guest", "guest_nice"}
    return sum(
        float(value)
        for name, value in zip(counter._fields, counter, strict=True)
        if name not in excluded and math.isfinite(float(value)) and float(value) >= 0
    )


def _clean_process_name(value: object) -> str:
    name = _CONTROL_CHARS.sub("", str(value or "Unknown process")).strip()
    return name[:200] or "Unknown process"


def _network_errors(counters: Mapping[str, Any]) -> tuple[int, int]:
    errors = 0
    drops = 0
    for counter in counters.values():
        errors += max(0, int(getattr(counter, "errin", 0) or 0))
        errors += max(0, int(getattr(counter, "errout", 0) or 0))
        drops += max(0, int(getattr(counter, "dropin", 0) or 0))
        drops += max(0, int(getattr(counter, "dropout", 0) or 0))
    return errors, drops


class SystemCollector:
    """Collects data using cumulative counters, so sampling works across threads."""

    def __init__(self) -> None:
        self._previous_cpu: Any | None = None
        self._previous_net: Any | None = None
        self._previous_swap_out: int | None = None
        self._previous_net_errors: tuple[int, int] | None = None
        self._previous_interfaces: dict[str, Any] | None = None
        self._previous_mono: float | None = None
        self._previous_monitor_cpu: float | None = None
        self._previous_process_times: dict[tuple[int, float], tuple[float, float]] = {}
        self._cpu_values: list[float] = []

    def collect(self) -> SystemSnapshot:
        sampled_at = utc_timestamp()
        now_mono = time.monotonic()
        elapsed = now_mono - self._previous_mono if self._previous_mono is not None else None
        cpu_times = self._safe_value(psutil.cpu_times)
        cpu_percent = self._cpu_usage(cpu_times)
        memory = self._safe_value(psutil.virtual_memory)
        swap = self._safe_value(psutil.swap_memory)
        disk = self._safe_value(psutil.disk_usage, os.path.abspath(os.sep))
        network = self._safe_value(psutil.net_io_counters)
        interfaces = self._safe_value(psutil.net_io_counters, pernic=True) or {}
        processes = self._collect_processes(now_mono, elapsed, memory)
        monitor = self._collect_monitor_usage(now_mono, elapsed)

        receive_rate = _rate(
            getattr(network, "bytes_recv", None),
            getattr(self._previous_net, "bytes_recv", None),
            elapsed,
        )
        send_rate = _rate(
            getattr(network, "bytes_sent", None),
            getattr(self._previous_net, "bytes_sent", None),
            elapsed,
        )
        swap_out_rate = _rate(getattr(swap, "sout", None), self._previous_swap_out, elapsed)

        current_errors = _network_errors(interfaces)
        error_delta = self._safe_counter_delta(
            current_errors[0], self._previous_net_errors[0] if self._previous_net_errors else None
        )
        drop_delta = self._safe_counter_delta(
            current_errors[1], self._previous_net_errors[1] if self._previous_net_errors else None
        )

        pids = self._safe_value(psutil.pids, default=[]) or []
        metrics = Metrics(
            cpu_percent=cpu_percent,
            cpu_average=(sum(self._cpu_values) / len(self._cpu_values)) if self._cpu_values else None,
            memory_percent=self._finite(getattr(memory, "percent", None)),
            memory_available_bytes=self._integer(getattr(memory, "available", None)),
            memory_total_bytes=self._integer(getattr(memory, "total", None)),
            swap_percent=self._finite(getattr(swap, "percent", None)),
            swap_out_bytes_per_second=swap_out_rate,
            disk_percent=self._finite(getattr(disk, "percent", None)),
            disk_free_bytes=self._integer(getattr(disk, "free", None)),
            disk_total_bytes=self._integer(getattr(disk, "total", None)),
            network_receive_bytes_per_second=receive_rate,
            network_send_bytes_per_second=send_rate,
            network_errors_delta=error_delta,
            network_drops_delta=drop_delta,
            process_count=len(pids),
        )

        self._previous_cpu = cpu_times
        self._previous_net = network
        self._previous_swap_out = getattr(swap, "sout", None)
        self._previous_net_errors = current_errors
        self._previous_interfaces = interfaces
        self._previous_mono = now_mono

        return SystemSnapshot(
            timestamp=sampled_at,
            platform=platform.system() or "Unknown",
            platform_release=platform.release() or "Unknown",
            architecture=platform.machine() or "Unknown",
            logical_cpus=max(1, psutil.cpu_count(logical=True) or 1),
            metrics=metrics,
            monitor=monitor,
            processes=processes,
        )

    def _collect_monitor_usage(self, now_mono: float, elapsed: float | None) -> MonitorUsage:
        try:
            process = psutil.Process(os.getpid())
            cpu_times = process.cpu_times()
            cpu_seconds = float(cpu_times.user) + float(cpu_times.system)
            memory = int(process.memory_info().rss)
        except (psutil.Error, OSError, AttributeError, TypeError, ValueError):
            return MonitorUsage()

        cpu_percent = None
        if self._previous_monitor_cpu is not None and elapsed and elapsed > 0:
            delta = cpu_seconds - self._previous_monitor_cpu
            if delta >= 0:
                cpu_percent = min(100.0, max(0.0, delta / elapsed / max(1, psutil.cpu_count() or 1) * 100.0))
        self._previous_monitor_cpu = cpu_seconds
        return MonitorUsage(cpu_percent=cpu_percent, memory_bytes=max(0, memory))

    def _cpu_usage(self, current: Any | None) -> float | None:
        if current is None or self._previous_cpu is None:
            return None
        total_delta = _counter_sum(current) - _counter_sum(self._previous_cpu)
        busy_delta = _counter_busy(current) - _counter_busy(self._previous_cpu)
        if total_delta <= 0 or busy_delta < 0:
            return None
        result = max(0.0, min(100.0, 100.0 * busy_delta / total_delta))
        self._cpu_values.append(result)
        del self._cpu_values[:-5]
        return result

    def _collect_processes(
        self,
        now_mono: float,
        elapsed: float | None,
        memory: Any | None,
    ) -> list[ProcessInfo]:
        total_memory = getattr(memory, "total", 0) or 0
        observed: dict[tuple[int, float], tuple[ProcessInfo, float, float]] = {}
        current_process_times: dict[tuple[int, float], tuple[float, float]] = {}

        try:
            psutil.process_iter.cache_clear()
            iterator = psutil.process_iter(
                attrs=["pid", "name", "memory_info", "cpu_times", "create_time", "status"],
                ad_value=None,
            )
            for process in iterator:
                try:
                    info = process.info
                    pid = int(info.get("pid") or process.pid)
                    created = info.get("create_time")
                    cpu_times = info.get("cpu_times")
                    memory_info = info.get("memory_info")
                    if pid <= 0 or created is None or cpu_times is None or memory_info is None:
                        continue
                    created = float(created)
                    identity = (pid, created)
                    cpu_seconds = float(cpu_times.user) + float(cpu_times.system)
                    current_process_times[identity] = (cpu_seconds, now_mono)
                    previous = self._previous_process_times.get(identity)
                    cpu_percent: float | None = None
                    if previous is not None and elapsed and elapsed > 0:
                        delta = cpu_seconds - previous[0]
                        if delta >= 0:
                            cpu_percent = min(
                                100.0, max(0.0, (delta / elapsed / max(1, psutil.cpu_count() or 1)) * 100.0)
                            )
                    rss = max(0, int(memory_info.rss))
                    memory_percent = (rss / total_memory * 100.0) if total_memory else 0.0
                    item = ProcessInfo(
                        pid=pid,
                        name=_clean_process_name(info.get("name")),
                        created_at=datetime.fromtimestamp(created, UTC)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z"),
                        cpu_percent=cpu_percent,
                        memory_bytes=rss,
                        memory_percent=max(0.0, min(100.0, memory_percent)),
                        status=str(info.get("status") or "unknown")[:40],
                    )
                    observed[identity] = (item, cpu_seconds, rss)
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                    OSError,
                    TypeError,
                    ValueError,
                    AttributeError,
                ):
                    continue
        except (psutil.Error, OSError):
            observed = {}
            current_process_times = {}

        self._previous_process_times = current_process_times
        by_cpu = sorted(
            (entry[0] for entry in observed.values()),
            key=lambda item: item.cpu_percent if item.cpu_percent is not None else -1.0,
            reverse=True,
        )[:_PROCESS_LIMIT]
        by_memory = sorted(
            (entry[0] for entry in observed.values()),
            key=lambda item: item.memory_bytes,
            reverse=True,
        )[:_PROCESS_LIMIT]
        unique = {item.pid: item for item in (*by_cpu, *by_memory)}
        return sorted(
            unique.values(),
            key=lambda item: (item.cpu_percent is not None, item.cpu_percent or 0),
            reverse=True,
        )[:30]

    @staticmethod
    def _safe_counter_delta(current: int, previous: int | None) -> int | None:
        if previous is None:
            return None
        return max(0, current - previous)

    @staticmethod
    def _finite(value: Any) -> float | None:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None:
            return None
        number = int(value)
        return number if number >= 0 else None

    @staticmethod
    def _safe_value(function: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except (psutil.Error, OSError, PermissionError, ValueError):
            return default
