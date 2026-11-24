import type { PlanSeat } from '@/api/types'

export interface ListedSeat { seat: string; state: PlanSeat['state']; problems: number }

/** The seats of an area with problems, most problems first, then by seat name. */
export function problemSeats(seats: Record<string, PlanSeat>, area: Set<string>): ListedSeat[] {
  return [...area].filter((k) => seats[k]?.problems)
    .map((k) => ({ seat: k, state: seats[k].state, problems: seats[k].problems ?? 0 }))
    .sort((a, b) => b.problems - a.problems || a.seat.localeCompare(b.seat, undefined, { numeric: true }))
}
