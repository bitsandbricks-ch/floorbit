/** Which seat numbers the plan writes: every seat or none. */
export type SeatLabels = 'all' | 'none'
/** A screen's choice (kiosk panes): follow the zoom, always number every seat, or never. */
export type LabelMode = 'auto' | 'all' | 'none'

// From this many pixels a seat holds its number at the classic size (model.ts NEAR_FROM). Below it
// nobody reads or counts to a seat: colour, rings and the tip say which one it is (Mike, #1471).
const FULL_FROM = 30
// Row letters name the rows instead of block tags (Mike, 2026-11-26): from a seat this small they still read.
const ROWS_FROM = 5
// Row letters stay small and quiet, the size of a seat number: at most this many screen pixels and
// about half a seat, but never under ROW_MIN pixels while a seat has room for that.
const ROW_PX = 11
const ROW_MIN = 7
const ROW_OF_SEAT = 0.55
// A forced number on a small seat fills about half its width.
const FIT = 0.5

export interface LabelPlan {
  seats: SeatLabels
  /** Font sizes in drawing units (they scale with the plan), for the svg's CSS variables. */
  num: number
  row: number
  /** Row labels are written at all. */
  rows: boolean
}

/** How to label a hall with seats of ``cell`` drawing units at ``s`` screen pixels per unit.
 *  Shapes and colour first (#1471): small row letters from about 5 px a seat (no block tags), and from 30 px every seat has its number. ``paper`` prints the
 *  row labels at half a seat, since a printout has no zoom. Status colours never change with it. */
export function labelPlan(cell: number, s: number, mode: LabelMode = 'auto', paper = false): LabelPlan {
  const seatPx = cell * s
  const classic = 11
  const row = paper ? cell * ROW_OF_SEAT : Math.min(ROW_PX / s, Math.max(cell * ROW_OF_SEAT, Math.min(ROW_MIN / s, cell * 0.95)))
  let seats: SeatLabels
  if (mode === 'none') seats = 'none'
  else if (mode === 'all' || seatPx >= FULL_FROM) seats = 'all'
  else seats = 'none'
  // Forced numbers on small seats: as big as the seat allows.
  const num = seatPx >= FULL_FROM ? classic : cell * FIT
  return { seats, num, row, rows: mode !== 'none' && (paper || seatPx >= ROWS_FROM) }
}

/** The CSS variables the plan's stylesheet reads for label sizes. Set on the svg, so zooming changes
 *  them without drawing the (memoised) seats again. */
export function labelStyle(plan: LabelPlan): Record<string, string> {
  return { '--seat-num': `${plan.num.toFixed(2)}px`, '--row-lbl': `${plan.row.toFixed(2)}px` }
}
