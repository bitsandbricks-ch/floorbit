import type { PlanCable, PlanDrawing, PlanShape, SeatViewData } from '@/api/types'
import { seatCenter } from './model'

type Pt = [number, number]
type Size = { w: number; h: number }

// The same numbers as floorbit/cable_plan.py: one seat in % of the plan, and how far beside a block its cables run.
const PITCH_X = 2.0
const PITCH_Y = 3.2
const TRUNK = 1.0

const pct = (size: Size, x: number, y: number): Pt => [round((x / size.w) * 100), round((y / size.h) * 100)]
const round = (n: number) => Math.round(n * 100) / 100
const same = (a: Pt, b: Pt) => Math.abs(a[0] - b[0]) < 0.01 && Math.abs(a[1] - b[1]) < 0.01

interface Box { l: number; r: number; t: number; b: number; cx: number; cy: number; sideways: boolean }

/** A seat block's seats as a box in % of the plan, turned like the block. */
function boxOf(shape: PlanShape, size: Size): Box {
  const a = (shape.rotation * Math.PI) / 180
  const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([sx, sy]) => {
    const dx = (sx * shape.w) / 2, dy = (sy * shape.h) / 2
    return pct(size, shape.cx + dx * Math.cos(a) - dy * Math.sin(a), shape.cy + dx * Math.sin(a) + dy * Math.cos(a))
  })
  const [cx, cy] = pct(size, shape.cx, shape.cy)
  return {
    l: Math.min(...corners.map((p) => p[0])), r: Math.max(...corners.map((p) => p[0])),
    t: Math.min(...corners.map((p) => p[1])), b: Math.max(...corners.map((p) => p[1])),
    cx, cy, sideways: Math.round(shape.rotation / 90) % 2 !== 0,
  }
}

/** The automatic route from a switch to a seat, as the server draws it (cable_plan._to_seat). */
export function toSeat(start: Pt, seat: Pt, box: Box | null): Pt[] {
  if (!box) return start[0] === seat[0] || start[1] === seat[1] ? [] : [[seat[0], start[1]]]
  const [sx, sy] = start
  if (box.sideways || (box.l <= sx && sx <= box.r)) {
    const top = box.t - (TRUNK * PITCH_Y) / 2
    const bottom = box.b + (TRUNK * PITCH_Y) / 2
    const [near, far] = sy < box.cy ? [top, bottom] : [bottom, top]
    if (box.sideways || (seat[1] < box.cy) === (sy < box.cy)) return [[sx, near], [seat[0], near]]
    const x = sx < box.cx ? box.l - (TRUNK * PITCH_X) / 2 : box.r + (TRUNK * PITCH_X) / 2
    return [[sx, near], [x, near], [x, far], [seat[0], far]]
  }
  const x = sx < box.cx ? box.l - (TRUNK * PITCH_X) / 2 : box.r + (TRUNK * PITCH_X) / 2
  return [[x, sy], [x, seat[1]]]
}

/** Drops repeated points and bends that are not bends, like the server's ``_tidy``. */
function tidy(points: Pt[]): Pt[] {
  const out: Pt[] = []
  for (const raw of points) {
    const p: Pt = [round(raw[0]), round(raw[1])]
    if (out.length && same(out[out.length - 1], p)) continue
    if (out.length >= 2) {
      const [a, b] = [out[out.length - 2], out[out.length - 1]]
      if ((a[0] === b[0] && b[0] === p[0]) || (a[1] === b[1] && b[1] === p[1])) { out[out.length - 1] = p; continue }
    }
    out.push(p)
  }
  return out
}

/** Seat cables drawn where the plan has their switch and seat now, not where the last cable plan
 *  said: a switch or block just moved (or still being dragged in Edit) takes its cables along at
 *  once instead of after the next answer from the server. Automatic routes are routed again; bends
 *  the crew placed stay, only the ends follow. */
export function followPlan(cables: PlanCable[], data: Pick<SeatViewData, 'switches' | 'size'> & { drawing: PlanDrawing | null }): PlanCable[] {
  const { drawing, size } = data
  if (!drawing) return cables
  const switches = new Map(data.switches.map((s) => [s.name.toLowerCase(), pct(size, s.x, s.y)]))
  const blocks = new Map<string, Box>()
  const blockOf = (seat: string) => {
    const shape = drawing.shapes.find((b) => b.cells.some((c) => c.seat === seat))
    if (!shape) return null
    if (!blocks.has(shape.name)) blocks.set(shape.name, boxOf(shape, size))
    return blocks.get(shape.name)!
  }
  return cables.map((c) => {
    if (c.kind !== 'lan' || !c.ref.seat || c.points.length < 2) return c
    const at = seatCenter(drawing, c.ref.seat)
    const sw = c.via ? null : switches.get((c.ref.switch ?? '').toLowerCase())
    const first = c.points[0], last = c.points[c.points.length - 1]
    const start = sw ?? first
    const end = at ? pct(size, at.x, at.y) : last
    if (same(start, first) && same(end, last)) return c
    // Through a patch panel the panel's leg stays as drawn; the rest follows the seat.
    if (c.manual || c.via) return { ...c, points: [start, ...c.points.slice(1, -1), end] }
    return { ...c, points: tidy([start, ...toSeat(start, end, blockOf(c.ref.seat)), end]) }
  })
}

/** ``label``: the fullest stretch of its line, where the count is shown (once per line, not per stretch). */
export interface Bundle { x1: number; y1: number; x2: number; y2: number; count: number; label?: boolean }

/** Where several cables run along the same line (in drawing units): one entry per stretch, with how
 *  many cables share it. Drawn as one wider band with a count, so a block's cables read as a bundle
 *  instead of a dozen lines on top of each other. Only straight runs across or down count. */
export function bundles(cables: PlanCable[], size: Size, least = 3): Bundle[] {
  const lines = new Map<string, [number, number][]>()
  for (const c of cables) {
    if (c.kind !== 'lan') continue
    const pts = c.points.map(([x, y]) => [round((x / 100) * size.w), round((y / 100) * size.h)] as Pt)
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]]
      const across = Math.abs(a[1] - b[1]) < 0.5, down = Math.abs(a[0] - b[0]) < 0.5
      if (across === down) continue        // a slanted run or no run at all
      const key = across ? `h${Math.round(a[1])}` : `v${Math.round(a[0])}`
      const [from, to] = across ? [a[0], b[0]] : [a[1], b[1]]
      if (!lines.has(key)) lines.set(key, [])
      lines.get(key)!.push([Math.min(from, to), Math.max(from, to)])
    }
  }
  const out: Bundle[] = []
  for (const [key, spans] of lines) {
    // Sweep along the line counting how many runs cover each stretch.
    const edges = spans.flatMap(([a, b]): [number, number][] => [[a, 1], [b, -1]]).sort((p, q) => p[0] - q[0] || q[1] - p[1])
    let count = 0, at = 0
    const at0 = Number(key.slice(1))
    for (const [pos, step] of edges) {
      if (count >= least && pos - at > 1) {
        out.push(key[0] === 'h' ? { x1: at, y1: at0, x2: pos, y2: at0, count } : { x1: at0, y1: at, x2: at0, y2: pos, count })
      }
      count += step
      at = pos
    }
  }
  // Neighbouring stretches with the same count are one run.
  const runs = out.reduce<Bundle[]>((acc, b) => {
    const p = acc[acc.length - 1]
    const across = b.y1 === b.y2
    const joins = p && p.count === b.count && (across
      ? p.y1 === p.y2 && p.y1 === b.y1 && p.x2 === b.x1
      : p.x1 === p.x2 && p.x1 === b.x1 && p.y2 === b.y1)
    if (joins) acc[acc.length - 1] = { ...p, x2: b.x2, y2: b.y2 }
    else acc.push(b)
    return acc
  }, [])
  // One count per line: on its fullest stretch (the longest, when two are as full).
  const best = new Map<string, Bundle>()
  const len = (b: Bundle) => Math.hypot(b.x2 - b.x1, b.y2 - b.y1)
  for (const b of runs) {
    const key = b.y1 === b.y2 ? `h${b.y1}` : `v${b.x1}`
    const p = best.get(key)
    if (!p || b.count > p.count || (b.count === p.count && len(b) > len(p))) best.set(key, b)
  }
  const shown = new Set(best.values())
  return runs.map((b) => (shown.has(b) ? { ...b, label: true } : b))
}

/** Where a cable meets its seat: on the seat's edge along the last run, so the plug shows next to
 *  the seat's number instead of hiding under it (drawing units). */
export function plugAt(c: PlanCable, size: Size, cell: number): Pt | null {
  if (c.kind !== 'lan' || c.points.length < 2) return null
  const [ax, ay] = c.points[c.points.length - 2], [bx, by] = c.points[c.points.length - 1]
  const a: Pt = [(ax / 100) * size.w, (ay / 100) * size.h], b: Pt = [(bx / 100) * size.w, (by / 100) * size.h]
  const len = Math.hypot(b[0] - a[0], b[1] - a[1])
  if (!len) return b
  const back = Math.min(len, cell * 0.45)
  return [b[0] - ((b[0] - a[0]) / len) * back, b[1] - ((b[1] - a[1]) / len) * back]
}
