import type { Gap } from './gaps'

/** A row of a seat block as the server keeps it (floorbit/seat_rows.py). */
export interface BlockRow {
  /** The row's own id in its block, a whole number as text: it stays when rows are reordered. */
  id: string
  seats: number
  shape: RowShape
  /** Empty space above the row, in seats (the first row's is ignored). */
  gap: number
  align: 'start' | 'middle' | 'end'
  shift: number
  /** Where people sit, of the way the row runs; '' is the shape's own default. */
  side: '' | 'left' | 'right'
  reverse: boolean
  col_gaps: Gap[]
  /** arc: degrees from the first seat to the last. */
  bend?: number
  /** u: three sides, l: two, in seats, first side first. */
  sides?: number[]
  /** path: points in seats. */
  path?: [number, number][]
}

export type RowShape = 'line' | 'arc' | 'u' | 'l' | 'path'
export const SHAPES: RowShape[] = ['line', 'arc', 'u', 'l', 'path']
export const MAX_ROWS = 50, MAX_SEATS = 200

/** How many rows, from a block that has them as a list or (a block's create form) as a number. */
export const rowCount = (rows: number | BlockRow[] | undefined) => (Array.isArray(rows) ? rows.length : Math.max(1, rows ?? 1))

/** An id none of ``rows`` has: one more than the highest. */
export function nextRowId(rows: Pick<BlockRow, 'id'>[]): string {
  return String(Math.max(0, ...rows.map((r) => Number(r.id)).filter((n) => Number.isFinite(n))) + 1)
}

/** A new straight row under the others, as long as the last one. */
export function newRow(rows: BlockRow[], seats?: number): BlockRow {
  const last = rows[rows.length - 1]
  return { id: nextRowId(rows), seats: seats ?? last?.seats ?? 10, shape: 'line', gap: 0, align: last?.align ?? 'start',
    shift: 0, side: '', reverse: false, col_gaps: [] }
}

/** Seats per side when a row becomes a U or an L: a U as wide as it's deep, an L with equal arms
 *  (the server's default_sides). */
export function defaultSides(shape: RowShape, seats: number): number[] | undefined {
  if (shape === 'u') {
    const side = seats >= 3 ? Math.max(1, Math.floor(seats / 4)) : 0
    return side ? [side, seats - 2 * side, side] : [0, seats, 0]
  }
  if (shape === 'l') return [Math.floor(seats / 2), seats - Math.floor(seats / 2)]
  return undefined
}

/** ``row`` with another shape, with what that shape needs filled in. */
export function withShape(row: BlockRow, shape: RowShape): BlockRow {
  const out: BlockRow = { ...row, shape }
  delete out.bend
  delete out.sides
  delete out.path
  if (shape === 'arc') out.bend = row.bend ?? 60
  if (shape === 'u' || shape === 'l') out.sides = defaultSides(shape, row.seats)
  if (shape === 'path') out.path = row.path ?? [[0, 0], [Math.ceil(row.seats / 2), 0], [Math.ceil(row.seats / 2), Math.floor(row.seats / 2)]]
  return out
}

/** ``row`` with ``seats`` seats: a U or L keeps its shape, the extra seats going on the middle or
 *  last side; gaps past the end go. */
export function withSeats(row: BlockRow, seats: number): BlockRow {
  const n = Math.min(MAX_SEATS, Math.max(1, Math.round(seats)))
  const out: BlockRow = { ...row, seats: n, col_gaps: row.col_gaps.filter((g) => g.after < n) }
  if (row.sides) {
    const sides = [...row.sides]
    const grow = row.shape === 'u' ? 1 : sides.length - 1
    sides[grow] = Math.max(0, sides[grow] + n - row.seats)
    out.sides = sides.reduce((a, b) => a + b, 0) === n ? sides : defaultSides(row.shape, n)
  }
  return out
}

/** ``rows`` with the row at ``from`` moved to ``to``; ids stay with their rows. */
export function moveRow(rows: BlockRow[], from: number, to: number): BlockRow[] {
  if (to < 0 || to >= rows.length || from === to) return rows
  const out = [...rows]
  const [row] = out.splice(from, 1)
  out.splice(to, 0, row)
  return out
}
