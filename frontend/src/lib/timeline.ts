import type { Finding, Snapshot } from "../types";

export interface TimelineEvent extends Finding {
  event_key: string;
}

/** Emit one timeline entry when a finding first appears or returns after clearing. */
export function deriveTimeline(samples: Snapshot[]): TimelineEvent[] {
  let active = new Set<string>();
  const events: TimelineEvent[] = [];
  for (const sample of [...samples].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))) {
    const current = new Map(sample.findings.map((finding) => [finding.id, finding]));
    for (const [id, finding] of current) {
      if (!active.has(id)) {
        events.push({ ...finding, event_key: `${id}-${finding.observed_at}` });
      }
    }
    active = new Set(current.keys());
  }
  return events.reverse();
}
