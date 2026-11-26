// The stats dashboard (floorbit/stats.py).
export interface StatsSample { t: number; down: number; up: number; online: number }
export interface StatsWindow { avg_bps: number; peak_bps: number; peak_at: number; online_max: number; samples: number }
export interface StatsUplink { switch_id: string; switch: string; port: string; bps: number; speed_bps: number | null; utilization: number | null }
export interface StatsTalker {
  seat: string | null
  switch_id: string
  switch: string
  port: string
  download_bps: number
  upload_bps: number
  bps: number
  nick?: string | null
}
export interface StatsData {
  monitoring: boolean
  interval: number
  last_poll: number | null
  now: (StatsSample & {
    ports_up: number; ports_down: number; ports_errors: number
    /** Every port read, and those up at some read of this event that are down now (#1421). */
    ports_total?: number; ports_lost?: number
  }) | null
  hour: StatsWindow | null
  day: StatsWindow | null
  peak: { bps: number; at: number } | null
  series: StatsSample[]
  uplinks: StatsUplink[]
  top: StatsTalker[]
}
