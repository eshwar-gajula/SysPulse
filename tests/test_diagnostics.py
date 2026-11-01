from datetime import UTC

from syspulse.diagnostics import analyze
from syspulse.models import ProcessInfo


def test_high_cpu_waits_for_one_minute_of_sustained_samples(interval_snapshots):
    short_burst = interval_snapshots(20, cpu=95.0)
    assert analyze(short_burst) == []

    sustained = interval_snapshots(32, cpu=95.0)
    findings = analyze(sustained)
    assert [finding.id for finding in findings] == ["cpu.sustained-high"]
    assert findings[0].severity == "warning"
    assert "at least 60 seconds" in findings[0].observation
    assert any("moving average" in evidence for evidence in findings[0].evidence)


def test_cpu_spike_below_threshold_breaks_sustained_run(interval_snapshots, snapshot_factory):
    # Use fresh, chronological samples so a brief dip resets the duration.
    from datetime import datetime, timedelta

    start = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [snapshot_factory(at=start + timedelta(seconds=index * 2), cpu=92.0) for index in range(31)]
    samples[-1] = snapshot_factory(at=start + timedelta(seconds=60), cpu=10.0)
    assert analyze(samples) == []


def test_process_evidence_is_reported_as_correlation(interval_snapshots):
    process = ProcessInfo(
        pid=51,
        name="worker",
        created_at="2026-01-01T00:00:00.000000Z",
        cpu_percent=21.5,
        memory_bytes=512 * 1024**2,
        memory_percent=6.0,
        status="running",
    )
    samples = interval_snapshots(32, cpu=94.0)
    samples[-1] = samples[-1].model_copy(update={"processes": [process]})
    finding = analyze(samples)[0]
    assert "may be contributing" in finding.possible_cause
    assert any("PID 51" in item for item in finding.evidence)
    assert "not proof" in finding.possible_cause


def test_process_memory_growth_needs_a_sustained_trend_and_does_not_claim_a_leak(
    snapshot_factory,
):
    from datetime import UTC, datetime, timedelta

    created_at = "2026-01-01T00:00:00.000000Z"
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def sample_with_process(index: int):
        timestamp = start + timedelta(seconds=index * 8)
        rss_mib = 100 if index < 5 else 100 + (index - 4) * 20
        process = ProcessInfo(
            pid=77,
            name="memory-worker",
            created_at=created_at,
            cpu_percent=0.0,
            memory_bytes=rss_mib * 1024**2,
            memory_percent=3.0,
            status="running",
        )
        return snapshot_factory(at=timestamp, processes=[process])

    brief = [sample_with_process(index) for index in range(10)]
    assert not any(finding.id.startswith("process.memory-growth") for finding in analyze(brief))

    sustained = [sample_with_process(index) for index in range(21)]
    finding = next(item for item in analyze(sustained) if item.id.startswith("process.memory-growth"))
    assert finding.severity == "warning"
    assert "RSS increased" in finding.observation
    assert "A leak is one possible explanation" in finding.possible_cause
    assert "before concluding" in finding.recommendation


def test_memory_usage_is_not_mislabeled_as_a_leak(snapshot_factory):
    high_use = snapshot_factory(
        memory=96.0, memory_available=8 * 1024**3, memory_total=32 * 1024**3, swap=0.0
    )
    finding = analyze([high_use])[0]
    assert finding.id == "memory.high-use"
    assert finding.severity == "info"
    assert "does not establish memory pressure" in finding.observation
    assert "not evidence of a memory leak" in finding.recommendation


def test_memory_pressure_requires_headroom_or_swap_evidence(snapshot_factory):
    enough_headroom = snapshot_factory(memory=96.0, memory_available=3 * 1024**3, memory_total=32 * 1024**3)
    assert analyze([enough_headroom])[0].severity == "info"

    pressure = snapshot_factory(
        memory=98.5, memory_available=100 * 1024**2, memory_total=8 * 1024**3, swap_out_rate=8 * 1024**2
    )
    finding = analyze([pressure])[0]
    assert finding.severity == "critical"
    assert finding.id == "memory.high-use"
    assert "does not establish a memory leak" in finding.possible_cause


def test_disk_and_interface_threshold_findings(snapshot_factory):
    current = snapshot_factory(disk=98.0, net_errors=2, net_drops=3)
    findings = analyze([current])
    by_id = {item.id: item for item in findings}
    assert by_id["disk.low-space"].severity == "critical"
    assert by_id["network.errors-or-drops"].severity == "warning"
    assert "2 new error(s)" in by_id["network.errors-or-drops"].observation


def test_no_findings_for_healthy_sample(snapshot_factory):
    current = snapshot_factory(cpu=30.0, memory=61.0, disk=70.0)
    assert analyze([current]) == []
