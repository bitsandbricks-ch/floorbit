import type { PlanCell } from '@/api/types'

/** Which seat numbers the plan writes: every seat, only the first and last of each row, or none. */
export type SeatLabels = 'all' | 'ends' | 'none'
/** A screen's choice (kiosk panes): follow the zoom, always number every seat, or never. */
export type LabelMode = 'auto' | 'all' | 'none'

// Screen pixels: below this a letter can't be read from a few metres away.
const READABLE = 9
// From this many pixels a seat holds its number at the classic size (model.ts NEAR_FROM).
const FULL_FROM = 30
// A two or three digit number fits in a seat at about half its width.
const FIT = 0.5
// Below this many pixels a seat is a speck (model.ts FAR_BELOW): the block summaries take over.
const ENDS_FROM = 12

export interface LabelPlan {
  seats: SeatLabels
  /** Font sizes in drawing units (they scale with the plan), for the svg's CSS variables. */
  num: number
  end: number
  row: number
  /** Row letters are written at all. */
  rows: boolean
}

/** How to label a hall with seats of ``cell`` drawing units at ``s`` screen pixels per unit.
 *  Up close every seat has its number; zoomed out the numbers shrink to fit the seat as long as they
 *  stay readable, then only the row ends keep one (so a seat can still be counted to), and far out
 *  only the block summaries remain. Status colours never change with it. */
export function labelPlan(cell: number, s: number, mode: LabelMode = 'auto'): LabelPlan {
  const seatPx = cell * s
  const classic = 11
  const fitted = cell * FIT
  // Big enough to read on screen, but never larger than what fits in the seat.
  const num = seatPx >= FULL_FROM ? classic : Math.min(fitted, Math.max(classic, READABLE / s))
  const row = Math.min(cell, Math.max(cell * 0.6, 12 / s))
  const end = Math.max(classic, 11 / s)
  let seats: SeatLabels
  if (mode === 'none') seats = 'none'
  else if (mode === 'all' || num * s >= READABLE) seats = 'all'
  else if (seatPx >= ENDS_FROM) seats = 'ends'
  else seats = 'none'
  // Forced numbers on tiny seats: as big as the seat allows.
  return { seats, num: mode === 'all' && seats === 'all' && num * s < READABLE ? fitted : num, end, row, rows: seatPx >= ENDS_FROM }
}

/** The first and last seat of each row of a block (cells on the same line, in block coordinates). */
export function rowEnds(cells: Pick<PlanCell, 'seat' | 'x' | 'y'>[]): Set<string> {
  const rows = new Map<number, Pick<PlanCell, 'seat' | 'x'>[]>()
  for (const c of cells) {
    const key = Math.round(c.y)
    const row = rows.get(key)
    if (row) row.push(c)
    else rows.set(key, [c])
  }
  const out = new Set<string>()
  for (const row of rows.values()) {
    const sorted = [...row].sort((a, b) => a.x - b.x)
    out.add(sorted[0].seat)
    out.add(sorted[sorted.length - 1].seat)
  }
  return out
}

/** The CSS variables the plan's stylesheet reads for label sizes. Set on the svg, so zooming changes
 *  them without drawing the (memoised) seats again. */
export function labelStyle(plan: LabelPlan): Record<string, string> {
  return { '--seat-num': `${plan.num.toFixed(2)}px`, '--seat-end': `${plan.end.toFixed(2)}px`, '--row-lbl': `${plan.row.toFixed(2)}px` }
}
