import type { PlanShape } from '@/api/types'

/** Seats placed freely inside a block (floorbit/seat_layout.py): ``{"<row id>,<seat>": [x, y]}``,
 *  each seat's top-left corner in seats, in the block's own frame before it is turned; the block's
 *  x/y is the middle of the seats' box. */
export type SeatAt = Record<string, [number, number]>

// The row's own id (it stays when rows are reordered); older answers have none, so its place + 1.
const key = (shape: PlanShape, rc: [number, number]) => `${shape.row_list?.[rc[0]]?.row ?? rc[0] + 1},${rc[1]}`

/** Where every seat of a drawn block is now, in seats from the box's top-left corner. */
export function seatPlaces(shape: PlanShape, cell: number): SeatAt {
  const out: SeatAt = {}
  for (const c of shape.cells) {
    if (c.rc) out[key(shape, c.rc)] = [round((c.x + shape.w / 2) / cell), round((c.y + shape.h / 2) / cell)]
  }
  return out
}

/** ``rc``'s seat moved to ``to`` (seats, same frame), as the block's fields to save: the places
 *  starting at 0,0 again and the block's x/y (in % of a plan ``size`` units big) moved so every
 *  other seat stays where it is on the plan. */
export function moveSeat(shape: PlanShape, cell: number, size: { w: number; h: number }, rc: [number, number], to: [number, number]) {
  const at = { ...seatPlaces(shape, cell), [key(shape, rc)]: to }
  const xs = Object.values(at).map((p) => p[0]), ys = Object.values(at).map((p) => p[1])
  const left = Math.min(...xs), top = Math.min(...ys)
  const w = Math.max(...xs) + 1 - left, h = Math.max(...ys) + 1 - top
  // The box's middle moves by this much in the block's frame; turned onto the plan, it moves the block.
  const dx = (left + w / 2 - shape.w / cell / 2) * cell, dy = (top + h / 2 - shape.h / cell / 2) * cell
  const a = (shape.rotation * Math.PI) / 180
  const cx = shape.cx + dx * Math.cos(a) - dy * Math.sin(a), cy = shape.cy + dx * Math.sin(a) + dy * Math.cos(a)
  const seat_at: SeatAt = {}
  for (const [k, [x, y]] of Object.entries(at)) seat_at[k] = [round(x - left), round(y - top)]
  return { seat_at, x: round3((cx / size.w) * 100), y: round3((cy / size.h) * 100) }
}

/** The block's fields as they are now, to undo a seat's move with. */
export function placedNow(shape: PlanShape, cell: number, size: { w: number; h: number }) {
  return { seat_at: shape.free ? seatPlaces(shape, cell) : null, x: round3((shape.cx / size.w) * 100), y: round3((shape.cy / size.h) * 100) }
}

/** A point on the plan (drawing units) in the block's own frame, in seats from its box's top-left. */
export function toBlock(shape: PlanShape, cell: number, p: { x: number; y: number }): [number, number] {
  const a = (-shape.rotation * Math.PI) / 180
  const dx = p.x - shape.cx, dy = p.y - shape.cy
  return [(dx * Math.cos(a) - dy * Math.sin(a) + shape.w / 2) / cell, (dx * Math.sin(a) + dy * Math.cos(a) + shape.h / 2) / cell]
}

/** The block-frame point back on the plan, in drawing units. */
export function fromBlock(shape: PlanShape, cell: number, p: [number, number]) {
  const a = (shape.rotation * Math.PI) / 180
  const dx = p[0] * cell - shape.w / 2, dy = p[1] * cell - shape.h / 2
  return { x: shape.cx + dx * Math.cos(a) - dy * Math.sin(a), y: shape.cy + dx * Math.sin(a) + dy * Math.cos(a) }
}

const round = (v: number) => Math.round(v * 100) / 100
const round3 = (v: number) => Math.round(v * 1000) / 1000
