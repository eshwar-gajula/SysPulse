"""Start SysPulse bound to loopback by default."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from .config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local SysPulse system health dashboard.")
    parser.add_argument("--port", type=int, default=8000, help="Local HTTP port (default: 8000).")
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        load_settings()
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "syspulse.api:app",
        host="127.0.0.1",
        port=arguments.port,
        log_level="info",
        access_log=False,
        server_header=False,
        date_header=False,
        reload=False,
        timeout_keep_alive=5,
        limit_concurrency=32,
        backlog=64,
    )


if __name__ == "__main__":
    main()
