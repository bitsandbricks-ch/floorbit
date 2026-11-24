import type { PlanShape } from '@/api/types'

/** Where the space above row ``row`` is drawn, in the block's own frame, in seats from its box's
 *  top-left: halfway between the row above's lowest seat and this row's highest, as wide as both. */
export interface GapSpot { row: number; y: number; x1: number; x2: number }

export const GAP_LIMIT = 20

/** Rows of a drawn block, top first: each row's seats' box in seats from the block's top-left. */
export function rowBoxes(shape: PlanShape, cell: number) {
  const out: { top: number; bottom: number; left: number; right: number }[] = []
  for (const c of shape.cells) {
    if (!c.rc) continue
    const x = (c.x + shape.w / 2) / cell, y = (c.y + shape.h / 2) / cell
    const b = out[c.rc[0]]
    out[c.rc[0]] = b
      ? { top: Math.min(b.top, y), bottom: Math.max(b.bottom, y + 1), left: Math.min(b.left, x), right: Math.max(b.right, x + 1) }
      : { top: y, bottom: y + 1, left: x, right: x + 1 }
  }
  return out
}

/** One spot per row under another (the first row's space is ignored). */
export function gapSpots(shape: PlanShape, cell: number): GapSpot[] {
  const boxes = rowBoxes(shape, cell)
  const out: GapSpot[] = []
  for (let i = 1; i < boxes.length; i++) {
    const above = boxes[i - 1], here = boxes[i]
    if (!above || !here) continue
    out.push({ row: i, y: (above.bottom + here.top) / 2, x1: Math.min(above.left, here.left), x2: Math.max(above.right, here.right) })
  }
  return out
}

/** The space after dragging by ``by`` seats: within 0 and the server's limit, on quarter seats
 *  unless placed freely (Alt, or snapping off). */
export function draggedGap(was: number, by: number, free = false) {
  const v = Math.min(GAP_LIMIT, Math.max(0, was + by))
  return free ? Math.round(v * 100) / 100 : Math.round(v * 4) / 4
}

/** The block's x/y (in % of a plan ``size`` units big) once a row's space grows by ``grow`` seats:
 *  the box grows downwards, so its middle moves half of that, turned with the block. The rows above
 *  stay where they are on the plan. */
export function keepTop(shape: PlanShape, cell: number, size: { w: number; h: number }, grow: number) {
  const dy = (grow * cell) / 2
  const a = (shape.rotation * Math.PI) / 180
  const cx = shape.cx - dy * Math.sin(a), cy = shape.cy + dy * Math.cos(a)
  return { x: round3((cx / size.w) * 100), y: round3((cy / size.h) * 100) }
}

/** Which row of a drawn block a plan point (drawing units) is on: the row of the nearest seat. */
export function rowAt(shape: PlanShape, cell: number, p: [number, number]): number | null {
  let best: number | null = null, dist = Infinity
  for (const c of shape.cells) {
    if (!c.rc) continue
    const x = (c.x + shape.w / 2) / cell + 0.5, y = (c.y + shape.h / 2) / cell + 0.5
    const d = Math.hypot(x - p[0], y - p[1])
    if (d < dist) { dist = d; best = c.rc[0] }
  }
  return best
}

const round3 = (v: number) => Math.round(v * 1000) / 1000
