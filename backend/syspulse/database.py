"""Private, bounded SQLite history with parameterized queries."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import SystemSnapshot


class MetricsStore:
    def __init__(self, path: Path, retention_hours: int = 24) -> None:
        self.path = path
        self.retention_hours = retention_hours

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self.path.parent, 0o700)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS samples (
                    timestamp REAL PRIMARY KEY,
                    payload TEXT NOT NULL CHECK (json_valid(payload))
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_samples_timestamp ON samples(timestamp DESC)")
            connection.execute("PRAGMA user_version=1")
        if os.name != "nt" and self.path.exists():
            os.chmod(self.path, 0o600)

    def save(self, snapshot: SystemSnapshot) -> None:
        timestamp = (
            datetime.fromisoformat(snapshot.timestamp.replace("Z", "+00:00")).astimezone(UTC).timestamp()
        )
        payload = snapshot.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO samples(timestamp, payload) VALUES (?, ?)",
                (timestamp, payload),
            )

    def latest(self) -> SystemSnapshot | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM samples ORDER BY timestamp DESC LIMIT 1").fetchone()
        return SystemSnapshot.model_validate_json(row[0]) if row else None

    def history(self, *, seconds: int, limit: int) -> list[SystemSnapshot]:
        cutoff = datetime.now(UTC).timestamp() - seconds
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM samples WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        rows.reverse()
        return [SystemSnapshot.model_validate_json(row[0]) for row in rows]

    def prune(self) -> int:
        cutoff = datetime.now(UTC).timestamp() - self.retention_hours * 3600
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM samples WHERE timestamp < ?", (cutoff,))
        return max(0, cursor.rowcount)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA trusted_schema=OFF")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
