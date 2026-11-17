import type { PlanMark } from '@/api/types'
import { SCALE_MAX, SCALE_MIN } from '../markSize'
import { type Point, fromPct, snapPct, toPct } from './geometry'

/** The handles a selected mark has: a label or icon one corner to scale it, a zone its four
 *  corners, a wall its two ends. */
export type Handle = 'scale' | 'nw' | 'ne' | 'sw' | 'se' | 'a' | 'b'
type Size = { w: number; h: number }

const turn = (p: Point, c: Point, deg: number): Point => {
  if (!deg) return p
  const r = (deg * Math.PI) / 180, dx = p.x - c.x, dy = p.y - c.y
  return { x: c.x + dx * Math.cos(r) - dy * Math.sin(r), y: c.y + dx * Math.sin(r) + dy * Math.cos(r) }
}
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Where each of the mark's handles sits, in drawing units. ``corner`` is the outline's bottom
 *  right corner (unturned) for a label or icon. */
export function handlesOf(m: PlanMark, corner: Point): [Handle, Point][] {
  if (m.kind === 'zone') {
    const x2 = m.x + (m.w ?? 0), y2 = m.y + (m.h ?? 0)
    const c = { x: m.x + (m.w ?? 0) / 2, y: m.y + (m.h ?? 0) / 2 }, deg = m.rotation ?? 0
    return ([['nw', { x: m.x, y: m.y }], ['ne', { x: x2, y: m.y }], ['sw', { x: m.x, y: y2 }], ['se', { x: x2, y: y2 }]] as [Handle, Point][])
      .map(([h, p]) => [h, turn(p, c, deg)])
  }
  if (m.kind === 'wall') return [['a', { x: m.x, y: m.y }], ['b', { x: m.x2 ?? m.x, y: m.y2 ?? m.y }]]
  return [['scale', turn(corner, m, m.rotation ?? 0)]]
}

/** The mark with ``handle`` dragged to ``p`` (drawing units). ``from`` is where the handle was when
 *  the drag began. Snaps to the grid (or, for a scale, to tenths) unless ``free``. */
export function reshape(m: PlanMark, handle: Handle, p: Point, from: Point, size: Size, free: boolean): PlanMark {
  const grid = (q: Point): Point => {
    if (free) return q
    const v = toPct(size, q)
    return fromPct(size, { x: snapPct(v.x), y: snapPct(v.y) })
  }
  if (handle === 'scale') {
    const was = Math.hypot(from.x - m.x, from.y - m.y)
    if (!was) return m
    const raw = (m.scale ?? 1) * (Math.hypot(p.x - m.x, p.y - m.y) / was)
    const scale = clamp(free ? Math.round(raw * 100) / 100 : Math.round(raw * 10) / 10, SCALE_MIN, SCALE_MAX)
    return { ...m, scale }
  }
  if (handle === 'a' || handle === 'b') {
    const q = grid(p)
    const other = handle === 'a' ? { x: m.x2 ?? m.x, y: m.y2 ?? m.y } : { x: m.x, y: m.y }
    if (q.x === other.x && q.y === other.y) return m   // a wall needs two ends
    return handle === 'a' ? { ...m, x: q.x, y: q.y } : { ...m, x2: q.x, y2: q.y }
  }
  // A zone corner: the opposite corner stays put; the box never turns inside out or gets thinner
  // than half a seat. A turned zone is worked out in its own frame, then turned back.
  const deg = m.rotation ?? 0
  const c = { x: m.x + (m.w ?? 0) / 2, y: m.y + (m.h ?? 0) / 2 }
  const q = deg ? turn(p, c, -deg) : grid(p)
  const min = (size.w / 100) * 1
  const left = handle === 'nw' || handle === 'sw', top = handle === 'nw' || handle === 'ne'
  const x1 = m.x, y1 = m.y, x2 = m.x + (m.w ?? 0), y2 = m.y + (m.h ?? 0)
  const nx1 = left ? Math.min(q.x, x2 - min) : x1, nx2 = left ? x2 : Math.max(q.x, x1 + min)
  const ny1 = top ? Math.min(q.y, y2 - min) : y1, ny2 = top ? y2 : Math.max(q.y, y1 + min)
  const w = nx2 - nx1, h = ny2 - ny1
  if (!deg) return { ...m, x: nx1, y: ny1, w, h }
  // The new middle, turned back into the plan; the box is kept by its unturned top left corner.
  const mid = turn({ x: nx1 + w / 2, y: ny1 + h / 2 }, c, deg)
  return { ...m, x: mid.x - w / 2, y: mid.y - h / 2, w, h }
}

const r3 = (v: number) => Math.round(v * 1000) / 1000

/** The fields a reshape changes, as the server keeps them (percent of the plan), for a PUT. */
export function shapeBody(m: PlanMark, size: Size): Record<string, unknown> {
  if (m.kind === 'zone') {
    const a = toPct(size, m), d = toPct(size, { x: m.w ?? 0, y: m.h ?? 0 })
    return { x: r3(a.x), y: r3(a.y), w: r3(d.x), h: r3(d.y) }
  }
  if (m.kind === 'wall') {
    const a = toPct(size, m), b = toPct(size, { x: m.x2 ?? m.x, y: m.y2 ?? m.y })
    // Always sent, even empty: undoing a bend has to take it out again.
    const points = (m.points ?? []).map(([x, y]) => { const q = toPct(size, { x, y }); return [r3(q.x), r3(q.y)] })
    return { x: r3(a.x), y: r3(a.y), x2: r3(b.x), y2: r3(b.y), points }
  }
  return { scale: m.scale ?? 1 }
}

/** ``m`` with its corners at ``route`` (start, bends, end). */
export function withRoute(m: PlanMark, route: Point[]): PlanMark {
  const a = route[0], b = route[route.length - 1], mid = route.slice(1, -1)
  const out: PlanMark = { ...m, x: a.x, y: a.y, x2: b.x, y2: b.y }
  if (mid.length) out.points = mid.map((p) => [p.x, p.y])
  else delete out.points
  return out
}

/** Where a wall's corner lands when dragged to ``p``: on another wall's end or bend within ``reach``
 *  (so walls meet), else in 15° steps from ``from`` with Shift, else on the grid unless ``free``. */
export function snapCorner(p: Point, { anchors = [], reach = 0, from, angle = false, free = false, size }: {
  anchors?: Point[]; reach?: number; from?: Point; angle?: boolean; free?: boolean; size: Size
}): Point {
  let best: Point | null = null, dist = reach
  for (const q of anchors) {
    const d = Math.hypot(q.x - p.x, q.y - p.y)
    if (d <= dist) { best = q; dist = d }
  }
  if (best) return { x: best.x, y: best.y }
  if (angle && from) {
    const dx = p.x - from.x, dy = p.y - from.y
    const len = Math.hypot(dx, dy)
    const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 12)) * (Math.PI / 12)
    return { x: from.x + Math.cos(a) * len, y: from.y + Math.sin(a) * len }
  }
  if (free) return p
  const v = toPct(size, p)
  return fromPct(size, { x: snapPct(v.x), y: snapPct(v.y) })
}

/** How long a stretch is in seats (one grid cell each) and which way it points, in degrees
 *  counter-clockwise from east, the way a protractor reads: "4.5 · 90°". */
export function measure(a: Point, b: Point, cell: number): string {
  const len = Math.round((Math.hypot(b.x - a.x, b.y - a.y) / cell) * 10) / 10
  const deg = (Math.round((Math.atan2(-(b.y - a.y), b.x - a.x) * 180) / Math.PI) + 360) % 360
  return `${len} · ${deg}°`
}
