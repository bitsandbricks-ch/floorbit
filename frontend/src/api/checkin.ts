import type { PortAreaHint } from './portClients'

/** GET /api/checkin/info: the attendee check-in page's state (integrations/__init__.py). */
export interface CheckinInfo {
  open: boolean
  /** When the event starts, if the schedule says and it's still ahead. */
  opens_at: number | null
  ip: string | null
  checkin: { seat: string; username: string; wired?: 'pending' | 'verified' | 'not_wired' | 'unverified' | null } | null
  /** False when the browser says it's a phone or tablet (a hint only). */
  on_pc?: boolean
  /** The seat this PC is known to be at (its port is patched or learned), as a hint. */
  suggested_seat?: string | null
  /** True: the seat number alone is refused, the PIN from the seat card is needed. */
  pin_required?: boolean
  /** The short address to type on a PC (CHECKIN_ADDRESS), e.g. checkin.lan. */
  address?: string | null
  /** True: not through the local agent's front door, so the seat's port can't be learned from here. */
  outside?: boolean
  /** Outside on a PC: the agent's front door that knows this PC (url), and whether Floorbit is sure
   *  this browser is in the hall, so the page goes there by itself (sure). */
  hall?: { url: string; sure: boolean } | null
}

export type WiredState = 'pending' | 'verified' | 'not_wired' | 'unverified'

/** One row of GET /api/checkins/overview (integrations/checkin.py overview). */
export interface CrewCheckin {
  seat: string
  username: string | null
  ip: string | null
  mac: string | null
  device: 'pc' | 'mobile' | 'unknown'
  wired: WiredState
  /** The switch port the background lookup found for this check-in. */
  port: { switch: string; port: string } | null
  /** The port the seat is learned on (seat_ports.json), from a PIN check-in. */
  learned: { switch: string; port: string; learned_at: number; username?: string } | null
  pin: boolean
  /** The rough area the found port goes to, when the crew gave one. */
  area?: PortAreaHint | null
  checked_in_at: number | null
  verified_at: number | null
  /** What asking the switches said (docs/segments.md), when it says something for the crew. */
  lookup?: CheckinLookup | null
}

/** One check-in's switch lookup: a to-do when it couldn't ask. */
export interface CheckinLookup {
  state: 'found' | 'not_found' | 'todo' | 'closed' | 'error'
  todo?: 'no_segment' | 'segment_off' | 'no_core'
  vlan?: number
}

/** When check-ins may ask the switches (GET /api/checkins/lookup-window). */
export interface LookupWindow {
  open: boolean
  until: number | null
  why: 'doors' | 'by_hand' | 'activity' | null
  doors: number | null
  hours: number
  segments_on: number
}

export interface CheckinConflict {
  kind: 'shared' | 'plan' | 'taken' | 'area'
  seat: string
  /** The other seats on that port (shared), or the seat the patch plan gives it to (plan). */
  other: string[]
  switch: string
  port: string
}

/** GET /api/checkins/overview: the crew's Check-in page. */
export interface CheckinOverview {
  counts: Record<WiredState, number> & {
    checked_in: number; conflicts: number; learned: number; unused_pins: number; pins: number
  }
  rows: CrewCheckin[]
  conflicts: CheckinConflict[]
  portal: { fetches: { at: number; agent: string | null; done: number }[]; public_url: string | null }
  verifier: { last_error: string | null }
  lookups?: LookupWindow
}
