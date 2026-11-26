export type LogSeverity = 'emerg' | 'alert' | 'crit' | 'err' | 'warning' | 'notice' | 'info' | 'debug'

/** One syslog line as GET /api/logs answers it (floorbit/syslog.py). */
export interface SyslogLine {
  id: number
  ts: number
  facility: number
  severity: LogSeverity
  host: string | null
  program: string | null
  message: string
  sender: string
  device: string
  port: string | null
  seat: string | null
}

export type LogSource = 'syslog' | 'app' | 'audit' | `plugin:${string}`

export interface LogStatus {
  enabled: boolean
  listening: { port: number; tcp: boolean; bind: string } | null
  error: string | null
  counts: { received: number; kept: number; not_allowed: number; rate_limited: number }
  lines: number
  devices: string[]
  retention_hours: number
  demo: boolean
  last_id: number
  /** When the oldest kept line came (unix seconds): where the volume chart starts. */
  first_ts?: number | null
  /** Local agents that send the event network's syslog on (issue #2). */
  relayed?: { agent: string; at: number; lines: number; dropped: number; recent: boolean }[]
  sources: LogSource[]
  source: LogSource
  /** Logs plugins (Loki) that get every line, and how sending them goes. */
  stores?: { id: string; name: string; at?: number | null; sent?: number; error?: string | null }[]
  /** DHCP lease lines read from the syslog: a fresh IP to MAC source (docs/syslog.md). */
  leases?: { granted: number; released: number; last_at: number | null }
  query?: string
  query_error?: string
}

export interface LogsData {
  lines: SyslogLine[]
  status: LogStatus
}
