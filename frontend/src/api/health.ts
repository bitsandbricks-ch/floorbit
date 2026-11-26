import type { State, Tone } from './types'

// The service health wall (floorbit/health.py).
export type HealthKind = 'dhcp' | 'dns' | 'cache' | 'game' | 'uplink' | 'firewall' | 'web' | 'check' | 'other'
export interface HealthMetric {
  label: string
  value: number | string
  unit: string
  tone: Tone
}
export interface HealthCheck {
  id: string
  name: string
  kind: HealthKind
  status: State
  summary: string
  metrics: HealthMetric[]
  link: string
  plugin: string
  plugin_name: string
  since: number
  /** Until when its alerts are muted (issue #260), or null. */
  muted_until?: number | null
  /** How much of a pool is used, when the check counts one (a DHCP scope). */
  capacity?: { used: number; total: number }
  /** When that pool runs full at the rate of the last 15 minutes (issue #1061). `raised`: the wall
   *  made an "up" check "warn" for it. */
  forecast?: { used: number; total: number; pct: number; rate_per_min: number | null; full_in_min: number | null; level: State | null; raised?: boolean }
}
export interface HealthWall {
  checks: HealthCheck[]
  counts: Record<State, number>
  last_poll: number | null
  interval: number
  plugins: number
}
