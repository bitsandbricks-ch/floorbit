import type { PlanDrawing } from '@/api/types'
import type { View } from '../plan/model'
import { cellCenter, contentBox, planRows, type PlanFilter, type SharedView, type TourStops } from './model'

/** One stop of a hall plan tour: where the plan looks, under a name. A saved view brings its seat filter. */
export interface Stop { key: string; label: string; view: View; show?: PlanFilter }

/** The stops a tour goes through, in order: the pane's whole area, each seat block (top to bottom,
 *  left to right), then the saved views of this hall in the order the pane lists them. */
export function tourStops(drawing: PlanDrawing, home: View, stops: TourStops, views: SharedView[], hall: string,
  names: { whole: string; block: (b: PlanDrawing['shapes'][number]) => string }): Stop[] {
  const out: Stop[] = []
  if (stops.whole) out.push({ key: 'whole', label: names.whole, view: home })
  if (stops.blocks) {
    // Rows of blocks first, so a tour reads the hall like a page; a few units count as the same row.
    const blocks = drawing.shapes.map((b, i) => ({ b, i })).filter(({ b }) => b.cells.length)
      .sort((p, q) => Math.round(p.b.cy / 50) - Math.round(q.b.cy / 50) || p.b.cx - q.b.cx)
    for (const { b, i } of blocks) {
      const box = contentBox({ ...drawing, shapes: [b], marks: [] }, 24)
      if (box) out.push({ key: `block:${b.id ?? i}`, label: names.block(b), view: box })
    }
  }
  const byId = new Map(views.filter((v) => v.hall === hall).map((v) => [v.id, v]))
  for (const id of stops.views) {
    const v = byId.get(id)
    if (v) out.push({ key: `view:${id}`, label: v.name, view: v.view, show: v.show })
  }
  return out
}

/** The rows around ``seat``: its own and the one before and after it, so a new problem shows with
 *  enough of the hall around it to find it. Null when the seat isn't on the plan. */
export function problemView(drawing: PlanDrawing, seat: string): View | null {
  const block = drawing.shapes.find((b) => b.cells.some((c) => c.seat === seat))
  if (!block) return null
  const rows = planRows(drawing).filter((r) => r.block === block)
  const at = rows.findIndex((r) => r.cells.some((c) => c.seat === seat))
  const cells = at >= 0 ? rows.slice(Math.max(0, at - 1), at + 2).flatMap((r) => r.cells) : block.cells.filter((c) => c.seat === seat)
  const pts = cells.map((c) => cellCenter(drawing, block, c))
  const m = drawing.cell * 2
  const x0 = Math.min(...pts.map((p) => p.x)) - m, y0 = Math.min(...pts.map((p) => p.y)) - m
  const box = { x: x0, y: y0, w: Math.max(...pts.map((p) => p.x)) + m - x0, h: Math.max(...pts.map((p) => p.y)) + m - y0 }
  // A lone seat (no rows known) still gets some hall around it.
  const minW = drawing.cell * 12, minH = drawing.cell * 6
  if (box.w < minW) { box.x -= (minW - box.w) / 2; box.w = minW }
  if (box.h < minH) { box.y -= (minH - box.h) / 2; box.h = minH }
  return box
}

/** The seats that have a problem now and didn't before, newest last (none on the first look). */
export function freshProblems(before: ReadonlySet<string> | null, now: ReadonlySet<string>): string[] {
  return before ? [...now].filter((s) => !before.has(s)) : []
}
