export interface ForecastPoint { t: number; bps: number; low: number; high: number; basis: 'profile' | 'recent'; pct?: number }
export interface ForecastData {
  ready: boolean
  history_hours: number
  min_hours: number
  capacity_bps: number | null
  warn_pct: number
  lead_hours: number
  points: ForecastPoint[]
  alert: { t: number; bps: number; pct: number } | null
  level: number | null
  days: number
  peak: ForecastPoint | null
}

export interface CompareSide {
  peak_bps: number | null
  avg_bps: number | null
  bytes_moved: number
  online_max: number
  hours: number
  incidents: number
  outages: number | null
}
export interface ComparePoint { hour: number; now_avg_bps: number | null; then_avg_bps: number | null; now_online: number | null; then_online: number | null }
export interface CompareData {
  day: { now: CompareSide; then: CompareSide; series: ComparePoint[]; has_then: boolean }
  event: { name: string; id: string; then_start: number; elapsed_s: number; now: CompareSide; then: CompareSide; series: ComparePoint[] } | null
}
