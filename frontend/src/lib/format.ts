export function formatBytes(value: number | null, decimals = 1): string {
  if (value === null || !Number.isFinite(value) || value < 0) return "—";
  if (value < 1024) return `${Math.round(value)} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let amount = value;
  let unit = "B";
  for (const next of units) {
    amount /= 1024;
    unit = next;
    if (amount < 1024 || next === units.at(-1)) break;
  }
  return `${amount.toFixed(decimals)} ${unit}`;
}

export function formatRate(value: number | null): string {
  return value === null ? "—" : `${formatBytes(value)}/s`;
}

export function formatPercent(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "—" : `${value.toFixed(1)}%`;
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function relativeTime(value: string | null): string {
  if (!value) return "Waiting for first sample";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Waiting for first sample";
  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
  const minutes = Math.round(seconds / 60);
  return formatter.format(minutes, "minute");
}
