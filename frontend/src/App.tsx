import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cpu,
  Download,
  Gauge,
  HardDrive,
  LayoutDashboard,
  LoaderCircle,
  MemoryStick,
  Network,
  RefreshCw,
  ShieldCheck,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import { formatBytes, formatPercent, formatRate, formatTimestamp, relativeTime } from "./lib/format";
import type { DiagnosticEvent, Finding, Health, HealthStatus, HistoryPoint, HistoryResponse, ProcessInfo, Snapshot } from "./types";

interface DashboardData {
  health: Health;
  snapshot: Snapshot;
  samples: HistoryPoint[];
  events: DiagnosticEvent[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep a generic message when the response is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

function useDashboard(): {
  data: DashboardData | null;
  error: string | null;
  loading: boolean;
  refresh: (forceHistory?: boolean) => Promise<void>;
} {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const samplesRef = useRef<HistoryPoint[]>([]);
  const eventsRef = useRef<DiagnosticEvent[]>([]);
  const historyTimeRef = useRef(0);

  const refresh = useCallback(async (forceHistory = false) => {
    try {
      const [health, snapshot] = await Promise.all([
        getJson<Health>("/api/v1/health"),
        getJson<Snapshot>("/api/v1/snapshot"),
      ]);
      if (forceHistory || Date.now() - historyTimeRef.current >= 15_000) {
        const history = await getJson<HistoryResponse>("/api/v1/history?minutes=60&limit=1800");
        samplesRef.current = history.samples;
        eventsRef.current = history.events;
        historyTimeRef.current = Date.now();
      }
      setData({ health, snapshot, samples: samplesRef.current, events: eventsRef.current });
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to read the local monitor.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(true);
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return { data, error, loading, refresh };
}

function StatusPill({ status }: { status: HealthStatus }) {
  const labels: Record<HealthStatus, string> = {
    healthy: "System healthy",
    watch: "Review suggested",
    degraded: "Attention needed",
    critical: "Critical finding",
    warming_up: "Collecting baseline",
  };
  const Icon = status === "healthy" ? Check : status === "warming_up" ? LoaderCircle : AlertTriangle;
  return (
    <span className={`status-pill status-${status}`}>
      <Icon aria-hidden="true" size={15} className={status === "warming_up" ? "spin" : undefined} />
      {labels[status]}
    </span>
  );
}

function MetricCard({
  title,
  value,
  detail,
  icon: Icon,
  accent,
  percent,
}: {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  accent: string;
  percent?: number | null;
}) {
  const safePercent = percent == null ? null : Math.max(0, Math.min(100, percent));
  return (
    <article className={`metric-card accent-${accent}`}>
      <div className="metric-card-top">
        <span className="metric-label">{title}</span>
        <span className="metric-icon"><Icon aria-hidden="true" size={18} /></span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
      {percent !== undefined && percent !== null && (
        <div className="meter-track" aria-label={`${title} utilization`}>
          <div className="meter-fill" style={{ width: `${safePercent ?? 0}%` }} />
        </div>
      )}
    </article>
  );
}

function chartPoints(samples: HistoryPoint[], value: (sample: HistoryPoint) => number | null): string {
  if (samples.length < 2) return "";
  const left = 44;
  const right = 936;
  const top = 12;
  const bottom = 216;
  const lastIndex = samples.length - 1;
  return samples
    .map((sample, index) => {
      const amount = value(sample);
      if (amount === null || !Number.isFinite(amount)) return null;
      const x = left + (right - left) * (index / lastIndex);
      const y = bottom - (bottom - top) * (Math.max(0, Math.min(100, amount)) / 100);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((point): point is string => point !== null)
    .join(" ");
}

function MetricChart({ samples }: { samples: HistoryPoint[] }) {
  const cpu = chartPoints(samples, (sample) => sample.cpu_average ?? sample.cpu_percent);
  const memory = chartPoints(samples, (sample) => sample.memory_percent);
  const disk = chartPoints(samples, (sample) => sample.disk_percent);
  const ready = samples.length > 1 && (cpu.length > 0 || memory.length > 0 || disk.length > 0);
  const first = samples[0]?.timestamp;
  const last = samples.at(-1)?.timestamp;

  return (
    <div className="chart-shell">
      {ready ? (
        <svg className="history-chart" viewBox="0 0 960 248" role="img" aria-labelledby="chart-title chart-description">
          <title id="chart-title">System resource use in the last hour</title>
          <desc id="chart-description">CPU, memory, and disk utilization as percentages over up to one hour of stored samples.</desc>
          {[0, 25, 50, 75, 100].map((tick) => {
            const y = 216 - (204 * tick) / 100;
            return (
              <g key={tick}>
                <line className="chart-grid" x1="44" x2="936" y1={y} y2={y} />
                <text className="chart-axis" x="7" y={y + 4}>{tick}%</text>
              </g>
            );
          })}
          <polyline className="chart-line chart-cpu" points={cpu} />
          <polyline className="chart-line chart-memory" points={memory} />
          <polyline className="chart-line chart-disk" points={disk} />
        </svg>
      ) : (
        <div className="chart-empty">
          <Activity aria-hidden="true" size={24} />
          <p>{samples.length < 2 ? "A second sample will complete the timeline." : "Waiting for resource history."}</p>
          <span>Samples are collected locally every few seconds.</span>
        </div>
      )}
      <div className="chart-axis-footer">
        <span>{first ? formatTimestamp(first) : "No samples yet"}</span>
        <span>{samples.length.toLocaleString()} samples · up to 60-minute window</span>
        <span>{last ? formatTimestamp(last) : ""}</span>
      </div>
      <div className="chart-legend" aria-label="Chart legend">
        <span><i className="legend-dot dot-cpu" />CPU</span>
        <span><i className="legend-dot dot-memory" />Memory</span>
        <span><i className="legend-dot dot-disk" />Disk</span>
      </div>
    </div>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className={`finding-card finding-${finding.severity}`}>
      <div className="finding-mark" aria-hidden="true">
        {finding.severity === "info" ? <CircleHelp size={17} /> : <AlertTriangle size={17} />}
      </div>
      <div className="finding-content">
        <div className="finding-heading">
          <h3>{finding.title}</h3>
          <span className={`severity-tag severity-${finding.severity}`}>{finding.severity}</span>
        </div>
        <p>{finding.observation}</p>
        <details>
          <summary>View evidence and next steps <ChevronRight aria-hidden="true" size={15} /></summary>
          <div className="finding-detail">
            <div><strong>Possible cause</strong><p>{finding.possible_cause}</p></div>
            <div><strong>Evidence</strong><ul>{finding.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div><strong>Suggested next step</strong><p>{finding.recommendation}</p></div>
          </div>
        </details>
      </div>
    </article>
  );
}

function sortProcesses(processes: ProcessInfo[], sort: "cpu" | "memory"): ProcessInfo[] {
  return [...processes].sort((left, right) => {
    if (sort === "memory") return right.memory_bytes - left.memory_bytes;
    return (right.cpu_percent ?? -1) - (left.cpu_percent ?? -1);
  });
}

function ProcessTable({ processes }: { processes: ProcessInfo[] }) {
  const [sort, setSort] = useState<"cpu" | "memory">("cpu");
  const rows = useMemo(() => sortProcesses(processes, sort), [processes, sort]);
  return (
    <div className="table-scroll">
      <table>
        <caption className="sr-only">Processes using the most CPU or memory. Names and process IDs only.</caption>
        <thead><tr>
          <th scope="col">Process</th>
          <th scope="col">PID</th>
          <th scope="col" aria-sort={sort === "cpu" ? "descending" : "none"}>
            <button className="sort-button" onClick={() => setSort("cpu")}>CPU <span className="sort-unit">% of system</span></button>
          </th>
          <th scope="col" aria-sort={sort === "memory" ? "descending" : "none"}>
            <button className="sort-button" onClick={() => setSort("memory")}>Memory <span className="sort-unit">resident</span></button>
          </th>
          <th scope="col">State</th>
        </tr></thead>
        <tbody>
          {rows.map((process) => (
            <tr key={`${process.pid}-${process.name}`}>
              <td><span className="process-name"><span className="process-orb" />{process.name}</span></td>
              <td className="mono">{process.pid}</td>
              <td className="number-cell">{formatPercent(process.cpu_percent)}</td>
              <td className="number-cell">{formatBytes(process.memory_bytes)}</td>
              <td><span className="process-state"><i />{process.status.replaceAll("_", " ")}</span></td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td className="empty-row" colSpan={5}>No process details are available for this sample.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function Timeline({ events }: { events: DiagnosticEvent[] }) {
  const recent = [...events].reverse().slice(0, 6);
  return (
    <div className="timeline-list">
      {recent.length ? recent.map((event, index) => (
        <article key={`${event.finding.id}-${event.finding.observed_at}-${event.state}-${index}`} className="timeline-item">
          <span className={`timeline-pin pin-${event.finding.severity}`} />
          <div className="timeline-copy">
            <div className="timeline-meta"><span>{formatTimestamp(event.finding.observed_at)}</span><span className={`timeline-severity severity-${event.finding.severity}`}>{event.state}</span></div>
            <strong>{event.finding.title}{event.state === "cleared" ? " resolved" : ""}</strong>
            <p>{event.state === "cleared" ? "The finding no longer has current supporting evidence." : event.finding.observation}</p>
          </div>
        </article>
      )) : (
        <div className="timeline-empty"><Check aria-hidden="true" size={17} /><span>No diagnostic events recorded in this window.</span></div>
      )}
    </div>
  );
}

function Overview({ data }: { data: DashboardData }) {
  const { snapshot, health, samples, events } = data;
  const metric = snapshot.metrics;
  const memoryAvailable = metric.memory_available_bytes !== null && metric.memory_total_bytes !== null
    ? `${formatBytes(metric.memory_available_bytes)} available of ${formatBytes(metric.memory_total_bytes)}`
    : "Memory details are unavailable";
  const diskFree = metric.disk_free_bytes !== null && metric.disk_total_bytes !== null
    ? `${formatBytes(metric.disk_free_bytes)} free of ${formatBytes(metric.disk_total_bytes)}`
    : "Disk details are unavailable";
  const networkIssueCount = (metric.network_errors_delta ?? 0) + (metric.network_drops_delta ?? 0);

  return (
    <>
      <section className="metrics-grid" aria-label="Current system metrics">
        <MetricCard title="Processor" value={formatPercent(metric.cpu_percent)} detail={metric.cpu_average === null ? "Baseline in progress" : `5-sample average ${formatPercent(metric.cpu_average)}`} icon={Cpu} accent="mint" percent={metric.cpu_percent} />
        <MetricCard title="Memory" value={formatPercent(metric.memory_percent)} detail={memoryAvailable} icon={MemoryStick} accent="violet" percent={metric.memory_percent} />
        <MetricCard title="Root storage" value={formatPercent(metric.disk_percent)} detail={diskFree} icon={HardDrive} accent="amber" percent={metric.disk_percent} />
        <MetricCard title="Processes" value={metric.process_count.toLocaleString()} detail={`${snapshot.logical_cpus} logical CPU${snapshot.logical_cpus === 1 ? "" : "s"}`} icon={Terminal} accent="blue" />
      </section>

      <section className="secondary-metrics" aria-label="Network activity">
        <div className="secondary-title"><Network aria-hidden="true" size={17} /><span>Network activity</span><span className="secondary-window">since previous sample</span></div>
        <div className="network-rate"><ArrowDownToLine aria-hidden="true" size={16} /><span>Received</span><strong>{formatRate(metric.network_receive_bytes_per_second)}</strong></div>
        <div className="network-rate"><ArrowUpFromLine aria-hidden="true" size={16} /><span>Sent</span><strong>{formatRate(metric.network_send_bytes_per_second)}</strong></div>
        <div className={`interface-health ${networkIssueCount ? "interface-warning" : ""}`}>
          {metric.network_errors_delta === null || metric.network_drops_delta === null
            ? <Clock3 aria-hidden="true" size={15} />
            : networkIssueCount ? <AlertTriangle aria-hidden="true" size={15} /> : <Check aria-hidden="true" size={15} />}
          <span>{metric.network_errors_delta === null || metric.network_drops_delta === null
            ? "Interface counter baseline in progress"
            : networkIssueCount ? `${networkIssueCount} new interface issue${networkIssueCount === 1 ? "" : "s"}` : "No new interface errors or drops"}</span>
        </div>
      </section>

      <div className="content-grid">
        <section className="panel chart-panel" aria-labelledby="history-heading">
          <div className="panel-heading">
            <div><p className="eyebrow">RESOURCE HISTORY</p><h2 id="history-heading">System health timeline</h2></div>
            <span className="window-chip"><Clock3 aria-hidden="true" size={14} />Up to 60 minutes</span>
          </div>
          <MetricChart samples={samples} />
        </section>

        <section className="panel timeline-panel" id="timeline" aria-labelledby="timeline-heading">
          <div className="panel-heading">
            <div><p className="eyebrow">OBSERVATIONS</p><h2 id="timeline-heading">Recent events</h2></div>
            <span className="small-count">{events.filter((event) => event.state === "detected").length} detected</span>
          </div>
          <Timeline events={events} />
        </section>
      </div>

      <section className="panel findings-panel" id="diagnostics" aria-labelledby="findings-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">EXPLAINABLE ANALYSIS</p><h2 id="findings-heading">Diagnostic insights</h2></div>
          <span className="small-count">{snapshot.findings.length} active</span>
        </div>
        {snapshot.findings.length ? (
          <div className="finding-grid">{snapshot.findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}</div>
        ) : (
          <div className="all-clear">
            <span className="clear-icon"><ShieldCheck aria-hidden="true" size={19} /></span>
            <div><strong>{health.status === "warming_up" ? "Building a reliable baseline" : "No active findings"}</strong><p>{health.status === "warming_up" ? "SysPulse waits for enough samples before reporting sustained anomalies." : "No configured diagnostic rule has enough evidence to raise an alert."}</p></div>
          </div>
        )}
      </section>

      <section className="panel process-panel" id="processes" aria-labelledby="process-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">PROCESS INTELLIGENCE</p><h2 id="process-heading">Resource-heavy processes</h2></div>
          <span className="small-count">{metric.process_count.toLocaleString()} running</span>
        </div>
        <ProcessTable processes={snapshot.processes} />
        <p className="table-note"><ShieldCheck aria-hidden="true" size={14} /> Process command lines, usernames and environment variables are not collected.</p>
      </section>

      <section className="system-footer" id="system-info" aria-label="System information">
        <div className="system-foot-icon"><Gauge aria-hidden="true" size={17} /></div>
        <div><strong>{snapshot.platform} {snapshot.platform_release}</strong><span>{snapshot.architecture} · {snapshot.logical_cpus} logical CPUs · sampled {relativeTime(snapshot.timestamp)}</span></div>
        <span className="system-foot-note">Monitor footprint: {formatPercent(snapshot.monitor.cpu_percent)} CPU · {formatBytes(snapshot.monitor.memory_bytes)} RAM</span>
      </section>
    </>
  );
}

function App() {
  const { data, error, loading, refresh } = useDashboard();
  const [refreshing, setRefreshing] = useState(false);
  const snapshot = data?.snapshot;
  const status = data?.health.status ?? "warming_up";

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
    await refresh(true);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="SysPulse overview">
          <span className="brand-mark"><Activity aria-hidden="true" size={21} strokeWidth={2.5} /></span>
          <span className="brand-name">sys<span>pulse</span></span>
        </a>
        <div className="workspace-label">SYSTEM HEALTH</div>
        <nav className="side-nav" aria-label="Dashboard sections">
          <a className="nav-link nav-active" href="#overview"><LayoutDashboard aria-hidden="true" size={17} />Overview</a>
          <a className="nav-link" href="#timeline"><Clock3 aria-hidden="true" size={17} />Health timeline</a>
          <a className="nav-link" href="#diagnostics"><AlertTriangle aria-hidden="true" size={17} />Diagnostics</a>
          <a className="nav-link" href="#processes"><Terminal aria-hidden="true" size={17} />Processes</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card"><span className="privacy-icon"><ShieldCheck aria-hidden="true" size={17} /></span><strong>Private by design</strong><p>Metrics stay on this machine. SysPulse never stops a process.</p></div>
          <span className="sidebar-version">SYS PULSE <span>v1.0</span></span>
        </div>
      </aside>

      <main className="main-area" id="overview">
        <header className="topbar">
          <div className="breadcrumb"><span>Local machine</span><ChevronRight aria-hidden="true" size={14} /><strong>Overview</strong></div>
          <div className="topbar-actions">
            <span className="local-indicator"><i />LOCAL SESSION</span>
            <button className="icon-button refresh-button" onClick={() => void handleRefresh()} disabled={refreshing} aria-label="Refresh dashboard data" title="Refresh dashboard data">
              <RefreshCw aria-hidden="true" size={16} className={refreshing ? "spin" : undefined} />
            </button>
          </div>
        </header>

        <div className="page-content">
          <section className="welcome-row">
            <div>
              <p className="eyebrow">YOUR SYSTEM, EXPLAINED</p>
              <h1>System overview</h1>
              <p className="welcome-copy">A clear picture of your system’s health, with context when something looks unusual.</p>
            </div>
            <div className="overview-status">
              <StatusPill status={status} />
              <span className="sample-time">Last sample {relativeTime(data?.health.sampled_at ?? null)}</span>
            </div>
          </section>

          {error && (
            <div className="connection-banner" role="status">
              <AlertTriangle aria-hidden="true" size={17} />
              <span>{snapshot ? `The latest refresh failed: ${error}. Showing the last saved sample.` : `${error} Start the SysPulse service, then try again.`}</span>
              <button onClick={() => void handleRefresh()}>Retry</button>
            </div>
          )}

          {data ? <Overview data={data} /> : loading ? (
            <div className="loading-panel" role="status"><LoaderCircle aria-hidden="true" className="spin" size={23} /><span>Connecting to the local system monitor…</span></div>
          ) : (
            <div className="offline-panel">
              <span className="offline-icon"><Activity aria-hidden="true" size={21} /></span>
              <h2>Your local monitor is not responding</h2>
              <p>Start SysPulse on this machine, then reconnect. Your dashboard only requests data from the local service.</p>
              <code>python -m syspulse</code>
              <button className="primary-button" onClick={() => void handleRefresh()} disabled={refreshing}><RefreshCw aria-hidden="true" size={16} />Try again</button>
            </div>
          )}

          <footer className="page-footer">
            <span><ShieldCheck aria-hidden="true" size={14} />Read-only monitoring · No automatic actions</span>
            <span>Data kept locally for {data?.health.retention_hours ?? 24} hours</span>
            <div className="report-links"><span>Export report</span><a href="/api/v1/report" download><Download aria-hidden="true" size={14} />JSON</a><a href="/api/v1/report.html" download><Download aria-hidden="true" size={14} />HTML</a></div>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
