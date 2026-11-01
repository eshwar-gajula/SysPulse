from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from syspulse.models import Metrics, MonitorUsage, ProcessInfo, SystemSnapshot


def make_snapshot(
    *,
    at: datetime | None = None,
    cpu: float | None = 15.0,
    memory: float = 45.0,
    memory_available: int = 5 * 1024**3,
    memory_total: int = 8 * 1024**3,
    swap: float = 0.0,
    swap_out_rate: float | None = 0.0,
    disk: float = 42.0,
    receive_rate: float | None = 120.0,
    send_rate: float | None = 90.0,
    net_errors: int | None = 0,
    net_drops: int | None = 0,
    processes: list[ProcessInfo] | None = None,
    findings=None,
) -> SystemSnapshot:
    timestamp = (at or datetime.now(UTC)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return SystemSnapshot(
        timestamp=timestamp,
        platform="Linux",
        platform_release="6.8.0",
        architecture="x86_64",
        logical_cpus=4,
        metrics=Metrics(
            cpu_percent=cpu,
            cpu_average=cpu,
            memory_percent=memory,
            memory_available_bytes=memory_available,
            memory_total_bytes=memory_total,
            swap_percent=swap,
            swap_out_bytes_per_second=swap_out_rate,
            disk_percent=disk,
            disk_free_bytes=50 * 1024**3,
            disk_total_bytes=100 * 1024**3,
            network_receive_bytes_per_second=receive_rate,
            network_send_bytes_per_second=send_rate,
            network_errors_delta=net_errors,
            network_drops_delta=net_drops,
            process_count=10,
        ),
        monitor=MonitorUsage(cpu_percent=0.2, memory_bytes=52 * 1024**2),
        processes=processes or [],
        findings=findings or [],
    )


@pytest.fixture
def snapshot_factory():
    return make_snapshot


@pytest.fixture
def interval_snapshots(snapshot_factory):
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def create(count: int, seconds: int = 2, **values):
        return [
            snapshot_factory(at=start + timedelta(seconds=index * seconds), **values)
            for index in range(count)
        ]

    return create
