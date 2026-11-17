import type { SeatViewData } from '@/api/types'
import { MIN_W, type View } from '../model'
import { type ItemRef, outlineOf } from './geometry'

/** The view that shows all of ``refs`` with some room around them, keeping the screen's shape
 *  (``like``). Turned items count with their turned corners. Null when none of them is drawn. */
export function frameOf(data: SeatViewData, refs: ItemRef[], like: View): View | null {
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity
  for (const r of refs) {
    const o = outlineOf(data, r)
    if (!o) continue
    const a = (o.rotation * Math.PI) / 180, cos = Math.cos(a), sin = Math.sin(a)
    for (const [px, py] of [[o.box.x, o.box.y], [o.box.x + o.box.w, o.box.y], [o.box.x, o.box.y + o.box.h], [o.box.x + o.box.w, o.box.y + o.box.h]]) {
      const dx = px - o.centre.x, dy = py - o.centre.y
      const x = o.centre.x + dx * cos - dy * sin, y = o.centre.y + dx * sin + dy * cos
      x1 = Math.min(x1, x); y1 = Math.min(y1, y); x2 = Math.max(x2, x); y2 = Math.max(y2, y)
    }
  }
  if (x1 === Infinity) return null
  const ratio = like.h / like.w
  // A fifth more than the items need, never closer in than the plan's own zoom limit.
  const w = Math.max((x2 - x1) * 1.2, ((y2 - y1) * 1.2) / ratio, MIN_W * 2)
  const h = w * ratio
  return { x: (x1 + x2) / 2 - w / 2, y: (y1 + y2) / 2 - h / 2, w, h }
}
