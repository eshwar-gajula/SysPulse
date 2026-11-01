"""Summarize SysPulse's own sampled CPU share and resident memory."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration", type=int, default=300, help="Measure for 30–3600 seconds (default: 300)."
    )
    parser.add_argument(
        "--url", default="http://127.0.0.1:8000/api/v1/snapshot", help="Local snapshot endpoint."
    )
    arguments = parser.parse_args()
    if not 30 <= arguments.duration <= 3600:
        parser.error("--duration must be between 30 and 3600 seconds")
    parsed = urlsplit(arguments.url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        parser.error("--url must point to the loopback address 127.0.0.1")
    return arguments


def fetch_snapshot(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def main() -> int:
    arguments = parse_arguments()
    cpu_values: list[float] = []
    memory_values: list[float] = []
    deadline = time.monotonic() + arguments.duration
    print(f"Measuring the local monitor for {arguments.duration} seconds…", flush=True)
    try:
        while time.monotonic() < deadline:
            sample = fetch_snapshot(arguments.url)
            monitor = sample.get("monitor") or {}
            cpu = monitor.get("cpu_percent")
            memory = monitor.get("memory_bytes")
            if isinstance(cpu, (int, float)):
                cpu_values.append(float(cpu))
            if isinstance(memory, int) and memory >= 0:
                memory_values.append(float(memory))
            time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"Could not reach the local SysPulse API: {exc}", file=sys.stderr)
        return 1

    if not cpu_values or not memory_values:
        print(
            "The snapshot did not contain enough monitor measurements. Wait for two samples and try again.",
            file=sys.stderr,
        )
        return 1
    result = {
        "duration_seconds": arguments.duration,
        "samples": len(cpu_values),
        "cpu_percent_of_total_system_capacity": {
            "mean": round(statistics.fmean(cpu_values), 3),
            "p95": round(percentile(cpu_values, 0.95), 3),
            "maximum": round(max(cpu_values), 3),
        },
        "resident_memory_mib": {
            "mean": round(statistics.fmean(memory_values) / 1024**2, 2),
            "maximum": round(max(memory_values) / 1024**2, 2),
        },
        "note": "These measurements include polling overhead and describe this host and run only.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
