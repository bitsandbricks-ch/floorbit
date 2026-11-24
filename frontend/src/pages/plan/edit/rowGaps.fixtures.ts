import type { PlanShape } from '@/api/types'

// Two rows of three seats, one seat of space between them, 32 units a seat, its middle at 200,200.
export const twoRows: PlanShape = {
  id: 'b1', cx: 200, cy: 200, rotation: 0, w: 96, h: 96, name: 'A',
  cells: [0, 1].flatMap((r) => [0, 1, 2].map((c) => ({ x: c * 32 - 48, y: r * 64 - 48, seat: `${r}-${c}`, hit: false, on: null, rc: [r, c] as [number, number] }))),
  row_list: [{ id: 'b1:1', name: 'A', row: '1' }, { id: 'b1:2', name: 'B', row: '2' }],
}
