/** GET /api/report: the post-event report (issue #22). Nicks and IPs only when an admin asked. */
export interface ReportHour { t: number; online_max: number; checked_in: number; peak_bps: number; avg_bps: number; incidents?: number }
export interface ReportOutage { switch: string; times: number; down_s: number; longest_s: number; still_down: boolean }
export interface ReportPort {
  switch: string; port: string; seat: string | null; count: number; kinds: Record<string, number>; last: number
  nick?: string | null; ip?: string | null
}
export interface ReportIncident {
  title: string; seat: string | null; switch: string | null; circuit: string | null; team: string | null
  source: string; reports: number; start: number; end: number | null; status: string
  reported_by?: string | null; assignee?: string | null; nick?: string | null; ip?: string | null
}
export interface EventReport {
  event_name: string
  start: number | null
  end: number | null
  generated: number
  people: boolean
  may_add_people: boolean
  seats: number
  online_max: number
  checked_in_max: number
  peak: { bps: number; at: number } | null
  bytes_moved: number
  hours: ReportHour[]
  outages: ReportOutage[]
  problem_ports: ReportPort[]
  incidents: { total: number; fixed: number; open: number; from_seats: number; median_fix_s: number | null; median_take_s?: number | null; repeat_seats?: { seat: string; count: number }[]; seat_problems?: { problem: string; count: number }[]; items: ReportIncident[] }
}
