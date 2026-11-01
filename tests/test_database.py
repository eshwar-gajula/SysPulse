import os
import sqlite3
from datetime import UTC, datetime, timedelta

from syspulse.database import MetricsStore


def test_store_round_trips_untrusted_process_text_as_data(tmp_path, snapshot_factory):
    store = MetricsStore(tmp_path / "private" / "samples.sqlite3", retention_hours=24)
    store.initialize()
    malicious_label = "python'); DELETE FROM samples;-- <script>alert(1)</script>"
    snapshot = snapshot_factory()
    from syspulse.models import ProcessInfo

    record = ProcessInfo(
        pid=123,
        name=malicious_label,
        created_at="2026-11-01T10:00:00.000000Z",
        cpu_percent=0,
        memory_bytes=1,
        memory_percent=0,
        status="sleeping",
    )
    snapshot = snapshot.model_copy(update={"processes": [record]})
    store.save(snapshot)
    assert store.latest().processes[0].name == malicious_label
    assert len(store.history(seconds=3600, limit=10)) == 1
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1


def test_pruning_removes_only_expired_rows(tmp_path, snapshot_factory):
    store = MetricsStore(tmp_path / "metrics.sqlite3", retention_hours=24)
    store.initialize()
    old = snapshot_factory(at=datetime.now(UTC) - timedelta(days=2))
    recent = snapshot_factory()
    store.save(old)
    store.save(recent)
    assert store.prune() == 1
    assert store.latest().timestamp == recent.timestamp


def test_linux_database_file_permissions_are_private(tmp_path):
    store = MetricsStore(tmp_path / "private" / "metrics.sqlite3")
    store.initialize()
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
        assert store.path.parent.stat().st_mode & 0o777 == 0o700
