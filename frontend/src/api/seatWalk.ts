import type { SeatWalkInfo, WalkHallRow, WalkPort } from './types'

/** A mark the crew put on one seat during the walk (floorbit/seat_marks.py, issue #1356). */
export type SeatMarkKind = 'broken' | 'later' | 'skip'
export interface SeatMark { mark: SeatMarkKind; note: string | null; by: string; at: number }

/** One crew member's walk as the server keeps it (floorbit/seat_walkers.py): continued later, or
 *  taken over by someone else, where it got to. */
export interface KeptWalk {
  id: string; who: string; user: string | null; rows: string[]; order: 'rows' | 'snake'
  seat: string | null; started: number; updated: number; active: boolean; taken_from?: string
  done: { seat: string; switch: string; port: string; ms: number | null; at: number }[]
  failed: Record<string, { at: number; why: string | null }>
}

export interface WalkSeat {
  seat: string; port: WalkPort | null
  mark?: SeatMark | null
  /** A kept walk couldn't find this seat's port (and nothing found it since). */
  failed?: { at: number; why: string | null; who: string } | null
}

/** ``walked``: the part of ``found`` a walk found; the rest came from check-in (#1424). */
export type WalkRow = WalkHallRow & { marked?: number; failed?: number; walked?: number }

export type SeatWalkOverview = Omit<SeatWalkInfo, 'seats' | 'hall'> & {
  seats?: WalkSeat[]; hall?: WalkRow[]
  walks?: KeptWalk[]; me?: string; marks?: Record<string, SeatMark>
}
