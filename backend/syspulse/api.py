"""Local-only FastAPI application, REST API, and built dashboard delivery."""

from __future__ import annotations

import asyncio
import html
import logging
import platform
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, load_settings
from .models import (
    DiagnosticEvent,
    DiagnosticFinding,
    HealthResponse,
    HistoryPoint,
    HistoryResponse,
    SystemSnapshot,
)
from .service import MonitoringRuntime

logger = logging.getLogger("syspulse")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIRECTORY = PROJECT_ROOT / "frontend" / "dist"


def _health_status(snapshot: SystemSnapshot | None) -> str:
    if snapshot is None or snapshot.metrics.cpu_percent is None:
        return "warming_up"
    severities = {finding.severity for finding in snapshot.findings}
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "degraded"
    if "info" in severities:
        return "watch"
    return "healthy"


def _safe_report_html(report: dict[str, object]) -> str:
    snapshot = report.get("current")
    if not isinstance(snapshot, dict):
        raise ValueError("The report has no current snapshot.")
    metrics = snapshot.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    findings = report.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    items: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        evidence = finding.get("evidence") or []
        evidence_html = (
            "".join(f"<li>{html.escape(str(item))}</li>" for item in evidence if isinstance(item, str))
            if isinstance(evidence, list)
            else ""
        )
        items.append(
            "<article class='finding'><h2>"
            + html.escape(str(finding.get("title", "Finding")))
            + "</h2>"
            + "<p><strong>"
            + html.escape(str(finding.get("severity", "info")).title())
            + "</strong> · "
            + html.escape(str(finding.get("observation", "")))
            + "</p><p><strong>Possible cause:</strong> "
            + html.escape(str(finding.get("possible_cause", "")))
            + "</p><p><strong>Suggested next step:</strong> "
            + html.escape(str(finding.get("recommendation", "")))
            + "</p>"
            + ("<strong>Evidence</strong><ul>" + evidence_html + "</ul>" if evidence_html else "")
            + "</article>"
        )
    if not items:
        items.append("<p>No active findings at report time.</p>")
    generated = html.escape(str(report.get("generated_at", "")))
    system = html.escape(f"{snapshot.get('platform', 'Unknown')} {snapshot.get('platform_release', '')}")
    cards = []
    for label, key, suffix in (
        ("CPU", "cpu_percent", "%"),
        ("Memory", "memory_percent", "%"),
        ("Disk", "disk_percent", "%"),
    ):
        value = metrics.get(key)
        rendered = f"{float(value):.1f}{suffix}" if isinstance(value, (float, int)) else "Collecting"
        cards.append(
            f"<div class='metric'><span>{label}</span><strong>{html.escape(rendered)}</strong></div>"
        )
    process_rows = []
    processes = snapshot.get("processes") or []
    if isinstance(processes, list):
        for process in processes:
            if not isinstance(process, dict):
                continue
            name = html.escape(str(process.get("name", "Unknown process")))
            pid = html.escape(str(process.get("pid", "")))
            cpu = process.get("cpu_percent")
            memory = process.get("memory_bytes")
            cpu_text = f"{float(cpu):.1f}%" if isinstance(cpu, (float, int)) else "Collecting"
            memory_text = (
                f"{int(memory) / (1024**2):.1f} MiB" if isinstance(memory, (float, int)) else "Unavailable"
            )
            process_rows.append(
                f"<tr><td>{name}</td><td>{pid}</td><td>{html.escape(cpu_text)}</td><td>{html.escape(memory_text)}</td></tr>"
            )
    if not process_rows:
        process_rows.append("<tr><td colspan='4'>No process details available.</td></tr>")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SysPulse diagnostic report</title><style>"
        "body{font:16px system-ui,sans-serif;max-width:960px;margin:3rem auto;padding:0 1rem;color:#17222e;background:#f5f8fa}"
        "h1{font-size:2.2rem}.muted{color:#566575}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}"
        ".metric,.finding{background:white;border:1px solid #dbe3ea;border-radius:12px;padding:1rem;margin:.7rem 0}"
        ".metric span,.metric strong{display:block}.metric strong{font-size:1.7rem;margin-top:.5rem}"
        "table{width:100%;border-collapse:collapse;background:white}td,th{text-align:left;padding:.7rem;border-bottom:1px solid #dbe3ea}"
        "</style></head><body><h1>SysPulse diagnostic report</h1><p class='muted'>Generated "
        + generated
        + " · "
        + system
        + "</p><section class='metrics'>"
        + "".join(cards)
        + "</section><h2>Findings</h2>"
        + "".join(items)
        + "<h2>Resource-heavy processes</h2><table><thead><tr><th>Process</th><th>PID</th><th>CPU</th><th>RSS</th></tr></thead><tbody>"
        + "".join(process_rows)
        + "</tbody></table>"
        + "<p class='muted'>Recommendations are advisory. This report contains sampled local system metrics and process names.</p>"
        "</body></html>"
    )


def create_app(settings: Settings | None = None, *, collector=None) -> FastAPI:
    resolved_settings = settings or load_settings()
    runtime = MonitoringRuntime.create(resolved_settings, collector=collector)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime.store.initialize()
        try:
            runtime.latest_snapshot = await asyncio.to_thread(runtime.capture)
        except Exception:
            logger.warning("Initial system sample unavailable; monitoring will retry.")
        task = asyncio.create_task(runtime.sample_loop(), name="syspulse-sampler")
        app.state.runtime = runtime
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(
        title="SysPulse API",
        description="Read-only local system health and diagnostics.",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "::1", "[::1]", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        client_host = request.client.host if request.client is not None else None
        if client_host not in {"127.0.0.1", "::1", "testclient"}:
            response = JSONResponse(
                status_code=403, content={"detail": "SysPulse accepts local connections only."}
            )
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_runtime(request: Request) -> MonitoringRuntime:
        return request.app.state.runtime

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        active_runtime = get_runtime(request)
        snapshot = active_runtime.latest_snapshot
        return HealthResponse(
            status=_health_status(snapshot),
            sampled_at=snapshot.timestamp if snapshot else None,
            sample_interval_seconds=active_runtime.settings.sample_interval_seconds,
            retention_hours=active_runtime.settings.retention_hours,
            platform=platform.system() or "Unknown",
        )

    @app.get("/api/v1/snapshot", response_model=SystemSnapshot)
    async def snapshot(request: Request) -> SystemSnapshot:
        current = get_runtime(request).latest_snapshot
        if current is None:
            raise HTTPException(status_code=503, detail="A system snapshot is not available yet.")
        return current

    @app.get("/api/v1/diagnostics")
    async def diagnostics(request: Request) -> dict[str, object]:
        current = get_runtime(request).latest_snapshot
        if current is None:
            raise HTTPException(status_code=503, detail="Diagnostics are not available yet.")
        return {
            "status": _health_status(current),
            "observed_at": current.timestamp,
            "findings": [finding.model_dump(mode="json") for finding in current.findings],
        }

    @app.get("/api/v1/history", response_model=HistoryResponse)
    async def history(
        request: Request,
        minutes: Annotated[int, Query(ge=1, le=1440)] = 60,
        limit: Annotated[int, Query(ge=1, le=2000)] = 600,
    ) -> HistoryResponse:
        samples = await asyncio.to_thread(
            get_runtime(request).store.history, seconds=minutes * 60, limit=limit
        )
        events: list[DiagnosticEvent] = []
        active: dict[str, DiagnosticFinding] = {}
        for sample in samples:
            current_findings = {finding.id: finding for finding in sample.findings}
            for identifier, finding in current_findings.items():
                previous = active.get(identifier)
                if previous is None or previous.severity != finding.severity:
                    events.append(DiagnosticEvent(state="detected", finding=finding))
            for identifier, previous in active.items():
                if identifier not in current_findings:
                    events.append(
                        DiagnosticEvent(
                            state="cleared",
                            finding=previous.model_copy(update={"observed_at": sample.timestamp}),
                        )
                    )
            active = current_findings
        points = [
            HistoryPoint(
                timestamp=sample.timestamp,
                cpu_percent=sample.metrics.cpu_percent,
                cpu_average=sample.metrics.cpu_average,
                memory_percent=sample.metrics.memory_percent,
                disk_percent=sample.metrics.disk_percent,
            )
            for sample in samples
        ]
        return HistoryResponse(samples=points, events=events)

    async def report_data(request: Request) -> dict[str, object]:
        active_runtime = get_runtime(request)
        current = active_runtime.latest_snapshot
        if current is None:
            raise HTTPException(status_code=503, detail="A diagnostic report is not available yet.")
        samples = await asyncio.to_thread(active_runtime.store.history, seconds=3600, limit=2000)
        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "application": {"name": "SysPulse", "version": __version__},
            "system": {
                "platform": current.platform,
                "release": current.platform_release,
                "architecture": current.architecture,
                "logical_cpus": current.logical_cpus,
            },
            "current": current.model_dump(mode="json"),
            "findings": [finding.model_dump(mode="json") for finding in current.findings],
            "history": [sample.model_dump(mode="json") for sample in samples],
            "privacy_note": "No hostname, username, environment variables, process command lines, or credentials are included.",
        }

    @app.get("/api/v1/report")
    async def json_report(request: Request) -> Response:
        data = await report_data(request)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f'attachment; filename="syspulse-report-{stamp}.json"'},
        )

    @app.get("/api/v1/report.html", response_class=HTMLResponse)
    async def html_report(request: Request) -> HTMLResponse:
        data = await report_data(request)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        try:
            body = _safe_report_html(data)
        except (TypeError, ValueError):
            raise HTTPException(status_code=500, detail="The report could not be prepared.") from None
        return HTMLResponse(
            body,
            headers={"Content-Disposition": f'attachment; filename="syspulse-report-{stamp}.html"'},
        )

    if DASHBOARD_DIRECTORY.is_dir():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIRECTORY, html=True), name="dashboard")
    else:

        @app.get("/", include_in_schema=False)
        async def dashboard_not_built() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Dashboard assets are not built. Run npm install and npm run build in frontend/ first."
                },
            )

    return app


app = create_app()
