export type Severity = "info" | "warning" | "critical";
export type HealthStatus = "healthy" | "watch" | "degraded" | "critical" | "warming_up";

export interface Metrics {
  cpu_percent: number | null;
  cpu_average: number | null;
  memory_percent: number | null;
  memory_available_bytes: number | null;
  memory_total_bytes: number | null;
  swap_percent: number | null;
  swap_out_bytes_per_second: number | null;
  disk_percent: number | null;
  disk_free_bytes: number | null;
  disk_total_bytes: number | null;
  network_receive_bytes_per_second: number | null;
  network_send_bytes_per_second: number | null;
  network_errors_delta: number | null;
  network_drops_delta: number | null;
  process_count: number;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  created_at: string;
  cpu_percent: number | null;
  memory_bytes: number;
  memory_percent: number;
  status: string;
}

export interface MonitorUsage {
  cpu_percent: number | null;
  memory_bytes: number | null;
}

export interface Finding {
  id: string;
  severity: Severity;
  title: string;
  observation: string;
  possible_cause: string;
  evidence: string[];
  recommendation: string;
  observed_at: string;
}

export interface Snapshot {
  timestamp: string;
  platform: string;
  platform_release: string;
  architecture: string;
  logical_cpus: number;
  metrics: Metrics;
  monitor: MonitorUsage;
  processes: ProcessInfo[];
  findings: Finding[];
}

export interface HistoryPoint {
  timestamp: string;
  cpu_percent: number | null;
  cpu_average: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
}

export interface DiagnosticEvent {
  state: "detected" | "cleared";
  finding: Finding;
}

export interface Health {
  status: HealthStatus;
  sampled_at: string | null;
  sample_interval_seconds: number;
  retention_hours: number;
  platform: string;
}

export interface HistoryResponse {
  samples: HistoryPoint[];
  events: DiagnosticEvent[];
}
