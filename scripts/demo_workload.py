"""Run a bounded, opt-in CPU and memory workload for dashboard demonstrations."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import signal
import sys
import time


def burn_cpu(stop_event) -> None:
    value = 0
    while not stop_event.is_set():
        value = (value + 1) % 100_000_000


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-workers", type=int, default=1, help="Busy CPU workers (1–32; default: 1).")
    parser.add_argument(
        "--memory-mib", type=int, default=64, help="Resident memory to touch (0–512 MiB; default: 64)."
    )
    parser.add_argument(
        "--duration", type=int, default=75, help="Run duration in seconds (1–600; default: 75)."
    )
    arguments = parser.parse_args()

    available = os.cpu_count() or 1
    if not 1 <= arguments.cpu_workers <= min(32, available):
        parser.error(f"--cpu-workers must be between 1 and {min(32, available)} on this machine")
    if not 0 <= arguments.memory_mib <= 512:
        parser.error("--memory-mib must be between 0 and 512")
    if not 1 <= arguments.duration <= 600:
        parser.error("--duration must be between 1 and 600")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    workers = [
        context.Process(target=burn_cpu, args=(stop_event,), name=f"syspulse-demo-{index + 1}")
        for index in range(arguments.cpu_workers)
    ]

    memory = bytearray(arguments.memory_mib * 1024 * 1024)
    for offset in range(0, len(memory), 4096):
        memory[offset] = 1

    print(
        f"Starting {arguments.cpu_workers} CPU worker(s), touching {arguments.memory_mib} MiB, "
        f"for at most {arguments.duration} seconds. Press Ctrl+C to stop.",
        flush=True,
    )
    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop_event.set())
    started = time.monotonic()
    try:
        for worker in workers:
            worker.start()
        while not stop_event.is_set() and time.monotonic() - started < arguments.duration:
            time.sleep(0.2)
    finally:
        stop_event.set()
        for worker in workers:
            if worker.pid is not None:
                worker.join(timeout=3)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=2)
        signal.signal(signal.SIGINT, original_handler)
        memory.clear()
    elapsed = time.monotonic() - started
    print(f"Workload stopped after {elapsed:.1f} seconds; its child workers have exited.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted; exiting.", file=sys.stderr)
        raise SystemExit(130) from None
