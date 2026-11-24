import type { BlockRow, RowCables } from './rows'
import { blockSeats } from './rowShapes'

/** Rows this close (in seats) share a table: they touch, or leave only a gap for cables. */
export const TABLE_GAP = 1

/** Where a straight row's chairs go, as its ``side``: ``above`` or ``below`` the row on the plan
 *  (before the block is turned). Left of a row running right is up; turned over, the row's sides
 *  swap like the server's ``side_of`` (floorbit/seat_rows.py), so a flipped row stores the other one. */
export function sideFor(row: BlockRow, where: 'above' | 'below'): 'left' | 'right' {
  const up = row.flip ? 'right' : 'left'
  return where === 'above' ? up : up === 'left' ? 'right' : 'left'
}

/** The block's rows with their chairs set automatically (Mike, issue #1342): rows that share a
 *  table (touching, or with only a cable gap) sit on its outer sides; a row on its own faces its
 *  bigger gap, a block's edge counting as open floor. Only straight rows change: bent rows, U and L
 *  have their chairs inside by their shape. A row in the middle of three or more keeps its side. */
export function autoChairs(rows: BlockRow[]): BlockRow[] {
  const { at } = blockSeats(rows)
  const extent = at.map((seats) => {
    const ys = seats.map((p) => p[1])
    return ys.length ? { top: Math.min(...ys) - 0.5, bottom: Math.max(...ys) + 0.5 } : null
  })
  const straight = (i: number) => rows[i]?.shape === 'line' && !!extent[i]
  const gapAbove = (i: number) => {
    for (let k = i - 1; k >= 0; k--) if (extent[k]) return Math.max(0, extent[i]!.top - extent[k]!.bottom)
    return Infinity
  }
  const gapBelow = (i: number) => {
    for (let k = i + 1; k < rows.length; k++) if (extent[k]) return Math.max(0, extent[k]!.top - extent[i]!.bottom)
    return Infinity
  }
  // Runs of straight rows that share tables, top first.
  const tables: number[][] = []
  rows.forEach((_, i) => {
    if (!straight(i)) return
    const last = tables[tables.length - 1]
    if (last && last[last.length - 1] === i - 1 && gapAbove(i) <= TABLE_GAP) last.push(i)
    else tables.push([i])
  })
  const out = [...rows]
  for (const t of tables) {
    if (t.length === 1) {
      const i = t[0], above = gapAbove(i), below = gapBelow(i)
      if (above !== below) out[i] = { ...rows[i], side: sideFor(rows[i], above > below ? 'above' : 'below') }
      continue
    }
    const first = t[0], last = t[t.length - 1]
    out[first] = { ...rows[first], side: sideFor(rows[first], 'above') }
    out[last] = { ...rows[last], side: sideFor(rows[last], 'below') }
  }
  return out
}

/** Every row's cables set to plug in the same way ('' = Auto). */
export function withCables(rows: BlockRow[], cables: RowCables): BlockRow[] {
  return rows.map((r) => {
    const next = { ...r }
    delete next.cables
    return cables ? { ...next, cables } : next
  })
}
