import type { ServiceTags } from './serviceChecks'
import type { ServiceStatus } from './services'

/** The public network status page (issue #101), as GET /api/status-page gives it. */
export type StatusState = 'operational' | 'degraded' | 'outage' | 'maintenance' | 'unknown'

export interface StatusArea {
  hall: string
  block: string
  /** Row numbers, for example "1-3, 5". Empty when Floorbit only knows the nearest block. */
  rows: string
  seats: number | null
  switches?: string[]
}

export interface StatusUpdate {
  id: string
  at: number
  text: string
  state: StatusState | null
  area: string
}

/** One count of every service (issue #1037): the health wall's checks, each internet site a row. */
export interface ServiceSummaryRow {
  id: string; name: string; kind: string; status: ServiceStatus; summary: string; link: string; tags?: string[]
}
export interface ServiceSummary {
  rows: ServiceSummaryRow[]
  /** Every service's tags by id (issue #1337), also of one the wall hasn't polled yet. */
  tags?: ServiceTags
  total: number
  counts: Record<ServiceStatus, number>
  by_kind: Record<string, Record<ServiceStatus | 'total', number>>
}

export interface StatusPageData {
  state: StatusState
  auto_state: StatusState
  override: { state: StatusState; note: string; by: string | null; at: number } | null
  since: number | null
  /** What players notice (issue #1038): switches, firewall, no_firewall, internet_slow, internet_down, dns, dhcp. */
  reasons?: string[]
  areas: StatusArea[]
  crew_areas: StatusArea[]
  /** Areas whose switch came back in the last half hour, with switch names (issue #396). */
  recovered: StatusArea[]
  recovered_at: number | null
  crew_recovered: StatusArea[]
  updates: StatusUpdate[]
  checked_at: number
  /** Is /status switched on (Settings > Public)? */
  public: boolean
}
