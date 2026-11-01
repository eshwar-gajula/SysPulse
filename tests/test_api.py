from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from syspulse.api import create_app
from syspulse.config import Settings
from syspulse.models import DiagnosticFinding, ProcessInfo


class FakeCollector:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def collect(self):
        return self.snapshot


def test_local_read_only_api_health_snapshot_history_and_reports(tmp_path, snapshot_factory):
    settings = Settings(data_directory=tmp_path, sample_interval_seconds=60, retention_hours=24)
    script_like_name = "<script>alert(1)</script>"
    process = ProcessInfo(
        pid=123,
        name=script_like_name,
        created_at="2026-11-01T10:00:00.000000Z",
        cpu_percent=1.0,
        memory_bytes=512,
        memory_percent=0.1,
        status="sleeping",
    )
    app = create_app(
        settings,
        collector=FakeCollector(snapshot_factory(at=datetime.now(UTC), processes=[process])),
    )
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert health.headers["x-content-type-options"] == "nosniff"
        assert health.headers["x-frame-options"] == "DENY"

        snapshot = client.get("/api/v1/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.json()["platform"] == "Linux"
        assert snapshot.json()["metrics"]["process_count"] == 10

        history = client.get("/api/v1/history?minutes=5&limit=10")
        assert history.status_code == 200
        assert len(history.json()["samples"]) == 1
        assert set(history.json()["samples"][0]) == {
            "timestamp",
            "cpu_percent",
            "cpu_average",
            "memory_percent",
            "disk_percent",
        }
        assert history.json()["events"] == []

        json_report = client.get("/api/v1/report")
        assert json_report.status_code == 200
        assert 'attachment; filename="syspulse-report-' in json_report.headers["content-disposition"]
        assert "privacy_note" in json_report.json()
        assert "hostname" not in json_report.json()

        html_report = client.get("/api/v1/report.html")
        assert html_report.status_code == 200
        assert 'attachment; filename="syspulse-report-' in html_report.headers["content-disposition"]
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_report.text
        assert script_like_name not in html_report.text

        openapi = client.get("/api/openapi.json").json()
        assert {method for path in openapi["paths"].values() for method in path} == {"get"}


def test_input_bounds_and_host_validation(tmp_path, snapshot_factory):
    app = create_app(
        Settings(tmp_path, sample_interval_seconds=60), collector=FakeCollector(snapshot_factory())
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/history?minutes=0").status_code == 422
        assert client.get("/api/v1/history?limit=2001").status_code == 422
        assert client.get("/api/v1/history?minutes=1%20OR%201%3D1").status_code == 422
        assert client.get("/api/v1/health", headers={"host": "attacker.invalid"}).status_code == 400


def test_cors_is_limited_to_local_development_origins(tmp_path, snapshot_factory):
    app = create_app(
        Settings(tmp_path, sample_interval_seconds=60), collector=FakeCollector(snapshot_factory())
    )
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
        denied = client.get("/api/v1/health", headers={"origin": "https://attacker.example"})
        assert "access-control-allow-origin" not in denied.headers


def test_history_records_finding_detection_and_clearance(tmp_path, snapshot_factory):
    app = create_app(
        Settings(tmp_path, sample_interval_seconds=60),
        collector=FakeCollector(snapshot_factory(at=datetime.now(UTC))),
    )
    detected_at = datetime.now(UTC) - timedelta(seconds=5)
    older = snapshot_factory(at=detected_at, cpu=95)
    finding = DiagnosticFinding(
        id="cpu.sustained-high",
        severity="warning",
        title="Sustained high CPU",
        observation="CPU remained elevated for 60 seconds.",
        possible_cause="A busy process may be contributing.",
        evidence=["CPU above threshold."],
        recommendation="Review the process and workload.",
        observed_at=older.timestamp,
    )
    app.state.runtime.store.initialize()
    app.state.runtime.store.save(older.model_copy(update={"findings": [finding]}))

    with TestClient(app) as client:
        response = client.get("/api/v1/history?minutes=5&limit=10")

    assert response.status_code == 200
    events = response.json()["events"]
    assert [event["state"] for event in events] == ["detected", "cleared"]
    assert events[-1]["finding"]["observed_at"] >= finding.observed_at


def test_remote_client_addresses_are_rejected(tmp_path, snapshot_factory):
    app = create_app(
        Settings(tmp_path, sample_interval_seconds=60), collector=FakeCollector(snapshot_factory())
    )
    with TestClient(app, client=("203.0.113.10", 54321)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 403
    assert response.json()["detail"] == "SysPulse accepts local connections only."
