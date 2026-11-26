export type IncidentStatus = 'open' | 'assigned' | 'fixed'
export interface IncidentNote {
  by: string | null
  at: number
  text: string
}
/** Speed test at the seat (issue #99): Mbit/s and ms, nothing personal. */
export interface SpeedtestResult { down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; jitter_ms: number | null; at: number }

export interface SeatSnapshot {
  known: boolean
  reason?: string
  switch?: string
  port?: string
  link?: string | null
  speed_bps?: number | null
  duplex?: string | null
  error_rate?: number | null
  mac_seen?: boolean
  stale?: boolean
}
export interface Incident {
  id: string
  seat: string | null
  switch_id: string | null
  switch_name?: string
  circuit_id?: string | null
  circuit_name?: string
  title: string
  problem: string | null
  /** The problem on the Problems page it was made from (issue #882). */
  from_problem?: string | null
  /** When that problem ended; gone again if it came back (issue #882). */
  problem_over_at?: number | null
  team: string | null
  status: IncidentStatus
  assignee: string | null
  source: 'board' | 'helpdesk' | 'power' | 'discord'
  reported_by: string | null
  reports: number
  notes: IncidentNote[]
  snapshot: SeatSnapshot | null
  /** The latest speed test from the seat's help page (issue #99). */
  speedtest?: SpeedtestResult | null
  created_at: number
  updated_at: number
  /** When it was marked fixed; null while not fixed. */
  /** Dismissed as not a problem (issue #887): closed like a fixed one, with the reason. */
  dismissed?: { reason: 'not_a_problem'; by: string; at: number } | null
  /** Put aside until then (issue #887): out of the waiting queue, back by itself after. */
  snoozed_until?: number | null
  fixed_at?: number | null
  dispatched_at?: number | null
  taken_at?: number | null
  /** The attendee said on the help page that it works again (issue #372); the crew still decides. */
  seat_ok_at?: number | null
  /** The seat's switch is down right now (issue #386). */
  outage?: { switch: string; since: number } | null
  /** Filed while the seat's switch was down, and the switch is back since (issue #390). */
  back_up?: { switch: string; since: number } | null
  can_work: boolean
  can_assign: boolean
  /** The seat's crew note (issue #204). */
  seat_note?: { text: string; by: string | null; at: number } | null
}
export interface IncidentBoard {
  incidents: Incident[]
  teams: { id: string; name: string; depth: number }[]
  workable_teams: string[]
  assign_teams: string[]
  can_assign_any: boolean
  problems: string[]
}
export type IncidentPeople = Record<string, { username: string; display_name: string }[]>
export interface QrSeat {
  seat: string
  url: string
  image: string
  /** With check-in on: the PIN printed on this seat's card, which names the seat. */
  pin?: string | null
}

/** Open incidents per seat and per switch id (GET /api/incidents/markers), for the crew layer. */
export interface IncidentMarkers { seats: Record<string, number>; switches: Record<string, number> }
