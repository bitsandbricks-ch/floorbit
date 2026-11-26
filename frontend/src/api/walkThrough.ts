import type { Cable } from './cables'
import type { PortAreaHint } from './portClients'

export interface SharedPort { switch: string; port: string; seat: string; cable: string; macs: number; desk_switch: boolean }
/** Walking the row (issue #473): ports that came up since the walk began. */
export interface WalkUp { port: string; at: number; how: 'syslog' | 'poll'; area?: PortAreaHint | null }
export interface WalkWatch { ups: WalkUp[]; syslog: boolean; since: number }
/** The crew's walk-through check-in (floorbit/seat_walk.py). */
export interface WalkPort { switch: string; port: string; learned_at?: number; source?: 'walk' | 'checkin' }
export interface SeatWalkInfo {
  /** Where laptops in the hall reach the local agent, which identifies them (null: not known). */
  agent_url: string | null; through_agent?: boolean; switch_lookup: boolean; monitoring: boolean; keep_hours: number
  /** Local agents connected now (#1424): the "no agent" warning only shows at 0. */
  agents_connected?: number
  event: { id: string; name: string; status: string }
  rows?: string[]; row_names?: string[]; seats?: { seat: string; port: WalkPort | null }[]
  /** Every hall row: how far the walk got and who walks it now (#1000). */
  hall?: WalkHallRow[]
}
export interface WalkHallRow {
  id: string; name: string; block_label: string; naming: string; seats: number; found: number
  walker: { id: string; who: string; seat: string | null } | null
}
export interface SeatWalker { id: string; who: string; rows: string[]; seat: string | null }
/** ip: the page came through an agent, the laptop is known at once; else url: the agent to open once. */
export interface SeatWalkHello { hello: string; url?: string; ip?: string }
export interface SeatLocated {
  ok: boolean; retry: boolean; seat: string; ip: string | null; mac: string | null; how: 'switch' | 'snmp' | 'monitoring' | null
  ms: number; tries: number; stale: boolean; found: WalkPort | null
  steps: { step: 'mac' | 'switch' | 'snmp' | 'monitoring'; ok: boolean; how?: string | null }[]
  replaced?: string[]; plan_seat?: string | null
  /** Every step of this Locate (issue #1359) and the agent that saw the laptop. */
  trace?: import('./seatWalkTrace').TraceStep[]; agent?: string | null
  /** The switch's area doesn't hold this seat (issue #1094). */
  area_drift?: AreaDrift | null
}
export interface AreaDrift { kind: 'pin' | 'plan' | 'excluded'; switch: string; area: string[]; row: string }
export interface SeatAssigned { cable: Cable; changed: string[]; other_seat: string }
