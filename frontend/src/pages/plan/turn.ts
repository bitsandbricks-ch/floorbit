import type { PlanMark, SeatViewData } from '@/api/types'
import { parseBox, type View } from './model'

/** A point turned a quarter left: what was on top ends up on the left. */
const left = (x: number, y: number): [number, number] => [y, -x]

function turnMark(m: PlanMark): PlanMark {
  const [x, y] = left(m.x, m.y)
  switch (m.kind) {
    case 'wall': {
      const [x2, y2] = left(m.x2 ?? m.x, m.y2 ?? m.y)
      return { ...m, x, y, x2, y2, points: m.points?.map(([px, py]) => left(px, py)) }
    }
    case 'zone': {
      // A zone is a box from its corner, turned about its middle: turn the middle and swap the sides.
      const w = m.w ?? 0, h = m.h ?? 0
      const [cx, cy] = left(m.x + w / 2, m.y + h / 2)
      return { ...m, x: cx - h / 2, y: cy - w / 2, w: h, h: w }
    }
    default:
      // Text and icons stay upright so they can still be read.
      return { ...m, x, y }
  }
}

/** The plan turned a quarter left, for a box much wider than the hall (a tall hall on a wide screen).
 *  Blocks, marks, switches, panels and boards turn; seat numbers and row letters stay upright (the
 *  plan already turns them back by their block's rotation). The background picture is left out: an
 *  image can't follow. Other overlays (power, Wi-Fi, cables) are the caller's to leave out. */
export function turnPlan(data: SeatViewData): SeatViewData {
  const d = data.drawing
  if (!d) return data
  const turnedBox = turnView(parseBox(d.box))
  return {
    ...data,
    background: null,
    background_frame: null,
    drawing: {
      ...d,
      box: `${turnedBox.x} ${turnedBox.y} ${turnedBox.w} ${turnedBox.h}`,
      shapes: d.shapes.map((s) => {
        const [cx, cy] = left(s.cx, s.cy)
        return { ...s, cx, cy, rotation: s.rotation - 90 }
      }),
      marks: d.marks?.map(turnMark),
    },
    switches: data.switches.map((w) => { const [x, y] = left(w.x, w.y); return { ...w, x, y } }),
    panels: data.panels?.map((p) => { const [x, y] = left(p.x, p.y); return { ...p, x, y } }),
    boards: data.boards?.map((b) => { const [x, y] = left(b.x, b.y); return { ...b, x, y } }),
  }
}

/** A view of the upright plan, as the same part of the turned plan. */
export const turnView = (v: View): View => ({ x: v.y, y: -(v.x + v.w), w: v.h, h: v.w })

/** Turning helps when the hall is tall and the box wide (or the other way round), enough that the
 *  turned hall comes out clearly bigger. */
export function turnHelps(box: { w: number; h: number }, px: { w: number; h: number }): boolean {
  if (!box.w || !box.h || !px.w || !px.h) return false
  const fit = (w: number, h: number) => Math.min(px.w / w, px.h / h)
  return fit(box.h, box.w) > fit(box.w, box.h) * 1.25
}
