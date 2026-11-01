import assert from "node:assert/strict";
import test from "node:test";
import { deriveTimeline } from "./timeline.ts";
import type { Snapshot } from "../types.ts";

const snapshot = (timestamp: string, findingIds: string[]): Snapshot => ({
  timestamp,
  platform: "Linux",
  platform_release: "6.1",
  architecture: "x86_64",
  logical_cpus: 4,
  metrics: {
    cpu_percent: 10,
    cpu_average: 10,
    memory_percent: 50,
    memory_available_bytes: 1,
    memory_total_bytes: 2,
    swap_percent: 0,
    swap_out_bytes_per_second: 0,
    disk_percent: 30,
    disk_free_bytes: 1,
    disk_total_bytes: 2,
    network_receive_bytes_per_second: 0,
    network_send_bytes_per_second: 0,
    network_errors_delta: 0,
    network_drops_delta: 0,
    process_count: 2,
  },
  processes: [],
  findings: findingIds.map((id) => ({
    id,
    severity: "warning",
    title: id,
    observation: "Observed",
    possible_cause: "Possible cause",
    evidence: [],
    recommendation: "Review",
    observed_at: timestamp,
  })),
});

test("shows the start and recurrence of findings, but not every repeated sample", () => {
  const events = deriveTimeline([
    snapshot("2026-01-01T00:00:04Z", ["cpu"]),
    snapshot("2026-01-01T00:00:01Z", ["cpu"]),
    snapshot("2026-01-01T00:00:02Z", []),
    snapshot("2026-01-01T00:00:03Z", ["cpu"]),
  ]);
  assert.equal(events.length, 2);
  assert.equal(events[0]?.observed_at, "2026-01-01T00:00:03Z");
  assert.equal(events[1]?.observed_at, "2026-01-01T00:00:01Z");
});
