# SysPulse

**Explainable Linux system health, running locally.** SysPulse measures system and process activity, records a short private history, and explains sustained resource issues with the evidence behind each finding. It makes read-only observations; it never kills processes, changes system settings, reads command lines, or sends telemetry.

SysPulse is designed for Linux. The collector also runs on Windows and macOS for development and basic cross-platform metrics; use Linux to evaluate Linux-specific behavior.

## What it does

- Samples CPU, memory, swap, root filesystem, network throughput, interface errors and drops, and process resource use every two seconds.
- Uses cumulative counters and a five-sample CPU moving average; a CPU finding requires at least 60 seconds above 85% so a short spike does not become a sustained-load alert.
- Correlates a sustained system CPU finding with a busy process when available, and labels that relationship as a possible contributor rather than a proven cause.
- Separates high memory use from pressure: a high percentage alone is not called a leak. Low available memory and observed swap-out are reported as separate evidence. A separate 2-minute, 5-minute-window process trend flags sustained RSS growth and still describes a leak as one possible explanation, not a diagnosis.
- Keeps timestamped samples and findings in a local SQLite database with a configurable retention period (24 hours by default).
- Provides a responsive dashboard, a health timeline, process sorting, and downloadable JSON and HTML reports.
- Reports the monitor’s own CPU and resident memory footprint next to system details.

## Quick start on Linux

Requirements: Linux, Python 3.11 or newer, and Node.js 22.6 or newer with npm. The runtime does not require root, Docker, an external database, or an AI service.

```bash
git clone https://github.com/eshwar-gajula/SysPulse.git
cd SysPulse

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

cd frontend
npm ci
npm run build
cd ..

python -m syspulse
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The API schema is at [http://127.0.0.1:8000/api/openapi.json](http://127.0.0.1:8000/api/openapi.json). The server listens on `127.0.0.1` by default and does not expose a network-host option in its launcher.

### Dashboard development

In one terminal, start the backend from the project root after activating the virtual environment:

```bash
python -m syspulse
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies API requests to the loopback backend.

### Configuration

| Environment variable | Default | Allowed values | Purpose |
| --- | --- | --- | --- |
| `SYSPULSE_DATA_DIR` | Linux: `~/.local/state/SysPulse` (or `$XDG_STATE_HOME/SysPulse`) | Local writable directory | SQLite history location |
| `SYSPULSE_SAMPLE_INTERVAL` | `2` | `1`–`60` seconds | Sample cadence |
| `SYSPULSE_RETENTION_HOURS` | `24` | Whole number `1`–`168` | History retention |

On Linux, SysPulse creates its data directory with user-only permissions and the SQLite file with mode `0600`. On Windows it uses `%LOCALAPPDATA%\SysPulse`; on macOS it uses `~/Library/Application Support/SysPulse`. Report downloads contain observed process names and resource readings; review them before sharing.

### First run

The first system CPU percentage and the first network rates need a counter baseline. They are shown as unavailable until a later sample arrives. SysPulse waits for 60 seconds of elevated CPU samples before raising the sustained CPU diagnostic. The dashboard labels these states instead of presenting unmeasured values as zero.

## Reproducible workload and overhead experiment

The optional workload generator is bounded and runs only when you start it. It defaults to one CPU worker and 64 MiB of memory, accepts at most 32 workers, 512 MiB, and 10 minutes, and cleans up only the child processes it created. It does not deliberately exhaust memory.

In a separate Linux terminal with SysPulse running:

```bash
source .venv/bin/activate
python scripts/demo_workload.py --cpu-workers 1 --memory-mib 128 --duration 75
```

One worker demonstrates a process-level CPU reading. To try the system-level 60-second CPU rule, choose a number of workers close to the number of logical CPUs available to your machine; this creates sustained load across those workers. Observe the impact first and interrupt the experiment with `Ctrl+C` if it affects other work. The memory allocation demonstrates process RSS; it does not promise to cause memory pressure or a leak finding on a machine with sufficient available RAM.

To summarize SysPulse’s own sampled CPU and resident memory over five minutes:

```bash
python scripts/measure_overhead.py --duration 300
```

The script polls the local snapshot API and prints the sample count, mean and 95th-percentile CPU share (normalized to total system capacity), and mean and peak resident memory. Requests made by the experiment are included in the observed monitor load. Use the output from your own host in a portfolio claim; no universal overhead benchmark is claimed here.

## API

All endpoints are read-only:

| Endpoint | Description |
| --- | --- |
| `GET /api/v1/health` | Service state and sampling configuration |
| `GET /api/v1/snapshot` | Most recent metrics, sampled processes, monitor footprint, and active findings |
| `GET /api/v1/diagnostics` | Active findings with their current system status |
| `GET /api/v1/history?minutes=60&limit=1800` | Compact chart samples and detected/cleared events (`minutes` 1–1440; `limit` 1–2000) |
| `GET /api/v1/report` | Download a JSON report and one hour of history |
| `GET /api/v1/report.html` | Download an HTML summary |
| `GET /api/openapi.json` | API schema |

Potential findings describe observations, a possible cause, evidence, and safe next steps. Recommendations are intentionally advisory. No endpoint takes an action on the machine.

## Development and verification

```bash
# Python API, collector, rules, database, and security behavior
python -m pip install -e '.[dev]'
python -m pytest

# Dashboard unit checks, TypeScript, and optimized static build
cd frontend
npm ci
npm test
npm run build

# Dependency advisories
python -m pip install pip-audit
python -m pip_audit -r requirements-audit.txt
ruff check backend tests
npm audit --audit-level=high
```

The GitHub Actions workflows repeat backend checks, frontend tests/builds, dependency audits, and CodeQL analysis. The Python audit resolves the direct application and development requirements listed in `requirements-audit.txt`, separately from packages preinstalled in your environment. Local tests use synthetic snapshots for deterministic rule coverage plus a small read-only collector smoke check. Linux-specific metrics should additionally be reviewed on a Linux machine; see [SECURITY.md](SECURITY.md) and the verification boundary below.

### Verification boundary

SysPulse has no external service, AI provider, cloud account, or production deployment. This repository’s automated checks do not prove behavior on every Linux distribution, kernel, container, CPU quota, network driver, or permission configuration. psutil may omit process fields that the current user cannot read. Network rates and counters are aggregate interface statistics; a counter increase does not identify a root cause. CPU percentage is total machine capacity, so a single fully occupied core represents a smaller share on a multicore host. These findings are investigation aids, not fault attribution.

## Architecture

```text
psutil + platform counters
          │
          ▼
SystemCollector ──► deterministic diagnostic rules
          │                    │
          └──────────────┬─────┘
                         ▼
              local SQLite history
                         │
                         ▼
               FastAPI on loopback
                         │
                         ▼
           React + TypeScript dashboard
```

The collector uses psutil’s process iterator to tolerate processes disappearing during collection and calculates rates from cumulative counters. SQLite values are bound as query parameters; its database and parent directory are private on Linux. The API restricts accepted Host headers and browser origins, sends a restrictive content policy, has no write or process-control route, and is loopback-bound by the packaged launcher.

## Project checks and sources

- [psutil documentation](https://psutil.readthedocs.io/stable/) — platform and process counter semantics.
- [FastAPI documentation](https://fastapi.tiangolo.com/) — API lifecycle and server framework.
- [Vite guide](https://vite.dev/guide/) — React and TypeScript build workflow.
- [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html) — parameter substitution and local database interface.
