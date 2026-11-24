import type { PlanShape } from '@/api/types'
import type { BlockRow } from './rows'
import { blockSeats } from './rowShapes'

// Two rows of three seats, one seat of space between them, 32 units a seat, its middle at 200,200.
export const twoRows: PlanShape = {
  id: 'b1', cx: 200, cy: 200, rotation: 0, w: 96, h: 96, name: 'A',
  cells: [0, 1].flatMap((r) => [0, 1, 2].map((c) => ({ x: c * 32 - 48, y: r * 64 - 48, seat: `${r}-${c}`, hit: false, on: null, rc: [r, c] as [number, number] }))),
  row_list: [{ id: 'b1:1', name: 'A', row: '1' }, { id: 'b1:2', name: 'B', row: '2' }],
}

/** A drawn block for ``rows`` as the server would draw it (floorbit/seat_rows.py), its middle at
 *  ``cx``,``cy``, 32 units a seat. */
export function drawnBlock(rows: BlockRow[], cx = 200, cy = 200, rotation = 0): PlanShape {
  const { at, w, h } = blockSeats(rows)
  return {
    id: 'b1', cx, cy, rotation, w: w * 32, h: h * 32, name: 'A', row_list: rows.map((r) => ({ id: `b1:${r.id}`, name: r.id, row: r.id })),
    cells: at.flatMap((row, r) => row.map(([x, y], c) => ({ x: (x - 0.5) * 32 - (w * 32) / 2, y: (y - 0.5) * 32 - (h * 32) / 2, seat: `${r}-${c}`, hit: false, on: null, rc: [r, c] as [number, number] }))),
  }
}

export const aRow = (extra: Partial<BlockRow>): BlockRow => ({ id: '1', seats: 5, shape: 'line', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [], ...extra })
