"""Public response models shared by collection, API, and reports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metrics(PublicModel):
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    cpu_average: float | None = Field(default=None, ge=0, le=100)
    memory_percent: float | None = Field(default=None, ge=0, le=100)
    memory_available_bytes: int | None = Field(default=None, ge=0)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    swap_percent: float | None = Field(default=None, ge=0, le=100)
    swap_out_bytes_per_second: float | None = Field(default=None, ge=0)
    disk_percent: float | None = Field(default=None, ge=0, le=100)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    disk_total_bytes: int | None = Field(default=None, ge=0)
    network_receive_bytes_per_second: float | None = Field(default=None, ge=0)
    network_send_bytes_per_second: float | None = Field(default=None, ge=0)
    network_errors_delta: int | None = Field(default=None, ge=0)
    network_drops_delta: int | None = Field(default=None, ge=0)
    process_count: int = Field(ge=0)


class ProcessInfo(PublicModel):
    pid: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    created_at: str
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    memory_bytes: int = Field(ge=0)
    memory_percent: float = Field(ge=0, le=100)
    status: str = Field(max_length=40)


class MonitorUsage(PublicModel):
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    memory_bytes: int | None = Field(default=None, ge=0)


class DiagnosticFinding(PublicModel):
    id: str = Field(min_length=1, max_length=80)
    severity: Literal["info", "warning", "critical"]
    title: str = Field(min_length=1, max_length=160)
    observation: str = Field(min_length=1, max_length=500)
    possible_cause: str = Field(min_length=1, max_length=500)
    evidence: list[str] = Field(max_length=12)
    recommendation: str = Field(min_length=1, max_length=500)
    observed_at: str


class SystemSnapshot(PublicModel):
    timestamp: str
    platform: str
    platform_release: str
    architecture: str
    logical_cpus: int = Field(ge=1)
    metrics: Metrics
    monitor: MonitorUsage = Field(default_factory=MonitorUsage)
    processes: list[ProcessInfo] = Field(max_length=30)
    findings: list[DiagnosticFinding] = Field(default_factory=list, max_length=20)


class HealthResponse(PublicModel):
    status: Literal["healthy", "watch", "degraded", "critical", "warming_up"]
    sampled_at: str | None
    sample_interval_seconds: float
    retention_hours: int
    platform: str


class HistoryPoint(PublicModel):
    timestamp: str
    cpu_percent: float | None
    cpu_average: float | None
    memory_percent: float | None
    disk_percent: float | None


class DiagnosticEvent(PublicModel):
    state: Literal["detected", "cleared"]
    finding: DiagnosticFinding


class HistoryResponse(PublicModel):
    samples: list[HistoryPoint]
    events: list[DiagnosticEvent]
