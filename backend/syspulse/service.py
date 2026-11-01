"""Sampling lifecycle and in-memory access to the most recent sample."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .collector import SystemCollector
from .config import Settings
from .database import MetricsStore
from .diagnostics import analyze
from .models import SystemSnapshot

logger = logging.getLogger("syspulse.sampler")


@dataclass(slots=True)
class MonitoringRuntime:
    settings: Settings
    collector: SystemCollector
    store: MetricsStore
    latest_snapshot: SystemSnapshot | None = None
    sample_count: int = 0

    @classmethod
    def create(cls, settings: Settings, collector: SystemCollector | None = None) -> MonitoringRuntime:
        return cls(
            settings=settings,
            collector=collector or SystemCollector(),
            store=MetricsStore(settings.database_path, settings.retention_hours),
        )

    def capture(self) -> SystemSnapshot:
        snapshot = self.collector.collect()
        previous = self.store.history(seconds=360, limit=400)
        snapshot = snapshot.model_copy(
            update={"findings": analyze([*previous, snapshot], self.settings.sample_interval_seconds)}
        )
        self.store.save(snapshot)
        return snapshot

    async def sample_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.sample_interval_seconds)
            try:
                self.latest_snapshot = await asyncio.to_thread(self.capture)
                self.sample_count += 1
                if self.sample_count % 30 == 0:
                    await asyncio.to_thread(self.store.prune)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("A system sample could not be collected or stored.")
