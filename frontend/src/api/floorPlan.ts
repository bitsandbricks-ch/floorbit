import type { WiredState } from './checkin'
import type { SeatFirewall } from './firewalls'
import type { PlanDrawing } from './plan'
import type { PowerState } from './power'
import type { LinkLldp, LinkType } from './topology'

/** GET /api/plan (issue #55): every seat with one state, for the floor plan view. No nicks or IPs. */
export type SeatState = 'online' | 'offline' | 'unknown'

export interface PlanSeat {
  state: SeatState
  checked_in?: boolean
  taken?: boolean
  problems?: number
  bps?: number
  /** When the link last changed, if within the last 15 minutes (issue #171). */
  changed?: number
  /** The crew left a note on the seat (issue #180); its text is in SeatDetails. */
  note?: boolean
  /** The down switch or link that cuts the seat off (issue #950); crew only. */
  behind?: string
}

export interface PlanBlock {
  /** The seat block's id, the same as its shape's; missing on older answers. */
  id?: string
  name: string
  /** What people call it: its name, else its row letters ("C–D"); missing on older answers. */
  label?: string
  seats: number
  online: number
  problems: number
}

export interface PlanSwitch {
  id: string
  name: string
  status: string
  /** Added by hand on the plan (deleting removes it), not from the inventory (deleting unplaces it). */
  manual?: boolean
  x: number
  y: number
}

/** A patch panel placed on this plan (drawing units), with its port count and how many have a cable. */
export interface PlanPanel { name: string; x: number; y: number; ports: number; used: number }
/** GET /api/cable-plan?hall= (floorbit/cable_plan.py): the cables to draw, points in % of the plan. */
export interface PlanCable {
  key: string; kind: 'lan' | 'uplink' | 'power'; layer: string; points: [number, number][]; manual: boolean
  /** The crew has drawn this cable (bends or corners) rather than leaving it automatic. */
  drawn?: boolean
  /** straight: one line end to end (``bends`` kept for when it is angled again). */
  corners: 'square' | 'round' | 'straight'; via: string | null; label: string; media?: string; speed?: number | null
  /** The bends the crew placed (null: automatic route). */
  bends?: [number, number][] | null
  ref: { cable?: string | null; source?: string; switch?: string; port?: string; seat?: string; link?: string; circuit?: string }
}
export interface CablePlan { cables: PlanCable[]; panels: { name: string; x: number | null; y: number | null; ports: number }[]; auto: boolean }
export interface PlanLink { id: string; a: string; b: string; type: LinkType | ''; media: string; speed: number | null; issue: '' | 'down' | 'slow' }
/** GET /api/power/markers (floorbit/power.py): the boards and each circuit's cable, for the plan's power layer. */
/** GET /api/firewalls/seats (issue #470): the seats whose traffic isn't on its planned firewall. */
export interface FirewallSeats {
  enabled: boolean
  seats: Record<string, { now: string | null; intended: string | null; state: 'failover' | 'down' }>
}

export interface PowerMarkers {
  enabled: boolean
  boards: { id: string; name: string; x: number; y: number; state: PowerState }[]
  circuits: { id: string; name: string; board: string; state: PowerState; pct: number | null; seats: string[]; switches: string[] }[]
  counts: Partial<Record<PowerState, number>>
}

export interface SeatViewData {
  /** Each hall's totals, for the hall picker (issue #196). */
  halls: { id: string; name: string; seats: number; online: number; problems: number }[]
  hall: string
  drawing: PlanDrawing | null
  size: { w: number; h: number; cell: number }
  background: string | null
  /** Where the background sits (drawing units on the plan, % on a hall) and how see-through it is. */
  background_frame?: { x: number; y: number; w: number; h: number } | null
  background_opacity?: number | null
  /** Metres per seat (one grid cell), from calibrating; null when not known. */
  seat_m?: number | null
  switches: PlanSwitch[]
  /** Links between switches placed on this plan (issue #468); older servers send none. */
  links?: PlanLink[]
  /** Patch panels placed on this plan; older servers send none. */
  panels?: PlanPanel[]
  /** Power distribution boards placed on the plan (drawing units); none with power off. */
  boards?: { id: string; name: string; x: number; y: number }[]
  seats: Record<string, PlanSeat>
  blocks: PlanBlock[]
  monitoring: boolean
  checkin: boolean
  last_read: number | null
}

/** GET /api/plan/seats/<seat>: one seat for the inspector. nick, ip and mac only with seats.view. */
export interface SeatDetails {
  seat: string
  block: string
  state: SeatState
  bps: number | null
  switch: string | null
  port: string | null
  incidents: { id: string; title: string; status: string; created_at: number }[]
  /** Incidents fixed at this seat before, and the latest one (issue #330). */
  fixed_before?: { count: number; last: { title: string; fixed_at: number | null } | null }
  attention: { kind: string; title: string; since: number }[]
  /** The link over the last hours (issue #167): online at ``from`` (null: not read yet), then each change. */
  history?: { from: number; to: number; start: boolean | null; changes: [number, number][] }
  checked_in: boolean | null
  /** Crew only: the port lookup of the seat's check-in, when it has one. */
  checkin_wired?: WiredState
  last_read: number | null
  people: boolean
  /** May this account read and write the seat's note (incidents.work)? */
  crew: boolean
  note?: SeatNote | null
  /** The player's speed tests from the help page, newest first (issue #182); crew only. */
  speedtests?: SeatSpeedTest[]
  /** Which firewall the core sends the seat to (issue #470); crew only, null when no range covers it. */
  firewall?: SeatFirewall | null
  nick?: string | null
  ip?: string | null
  mac?: string | null
}

/** One speed test the player ran from the seat's help page (issue #99). */
export interface SeatSpeedTest { down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; jitter_ms?: number | null; at: number }

/** GET /api/plan/find: a player by nick, IP or MAC, and the hall their seat is in (issue #186). */
export interface PlayerHit { seat: string; nick: string; matched: string; hall: string }

/** A crew note on a seat (issue #180). */
export interface SeatNote { text: string; by: string | null; at: number }

/** One seat block for the Seats view's block panel (issue #174). */
export interface BlockDetails {
  id?: string
  name: string
  /** Its name, else its row letters (issue #1030). */
  label?: string
  hall: string
  seats: number
  online: number
  offline: number
  unknown: number
  checked_in: number | null
  bps: number
  problems: { seat: string; state: SeatState; problems: number }[]
  switches: { name: string; seats: number; online: number; status: string }[]
  no_port: number
}

/** One switch for the Seats view's switch panel (issue #176). */
export interface SwitchDetails {
  name: string
  status: string
  since: number | null
  model: string | null
  online: number
  seats: { seat: string; port: string; state: SeatState; problems: number }[]
  /** Its planned links (topology) and what LLDP or CDP sees on ports no link explains (issue #540). */
  links?: { id: string; port: string; to: string; to_port: string; type: LinkType | ''; speed: number | null; issue: '' | 'down' | 'slow'; lldp: LinkLldp | null }[]
  neighbours?: { port: string; remote: string; remote_port: string; protocol: string }[]
}
