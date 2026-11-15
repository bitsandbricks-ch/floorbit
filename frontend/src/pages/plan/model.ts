import type { PlanDrawing, PlanSeat } from '@/api/types'

/** The part of the plan in view, in plan coordinates (an SVG viewBox). */
export interface View { x: number; y: number; w: number; h: number }

/** How much to draw: block summaries far out, seat states in between, seat numbers up close. */
export type Density = 'far' | 'mid' | 'near'

// In screen pixels per seat: below 12 a seat is a speck, from 30 its number fits.
export const FAR_BELOW = 12
export const NEAR_FROM = 30
export const MIN_W = 120

export function parseBox(box: string): View {
  const [x, y, w, h] = box.split(/\s+/).map(Number)
  return { x, y, w, h }
}

/** Screen pixels per plan unit; the SVG keeps its aspect ratio, so the smaller side wins. */
export function scale(view: View, px: { w: number; h: number }) {
  if (!px.w || !px.h) return 0
  return Math.min(px.w / view.w, px.h / view.h)
}

export function density(cell: number, view: View, px: { w: number; h: number }): Density {
  const s = scale(view, px)
  if (!s) return 'mid'   // not measured yet (or a test): the middle level shows states
  const seat = cell * s
  if (seat < FAR_BELOW) return 'far'
  return seat >= NEAR_FROM ? 'near' : 'mid'
}

/** Zoom by `factor` (>1 is in) keeping the plan point `at` where it is on screen. */
export function zoom(view: View, factor: number, at: { x: number; y: number }, limit: View): View {
  const w = Math.min(Math.max(view.w / factor, MIN_W), limit.w * 2)
  const f = view.w / w
  const h = view.h / f
  return { x: at.x - (at.x - view.x) / f, y: at.y - (at.y - view.y) / f, w, h }
}

export function pan(view: View, dx: number, dy: number): View {
  return { ...view, x: view.x + dx, y: view.y + dy }
}

/** A view of `w` wide around one point, for jumping to a seat. */
export function around(point: { x: number; y: number }, w: number, like: View): View {
  const h = (w * like.h) / like.w
  return { x: point.x - w / 2, y: point.y - h / 2, w, h }
}

/** Where a seat's centre is on the plan, with the block's rotation applied. */
export function seatCenter(drawing: PlanDrawing, seat: string) {
  for (const b of drawing.shapes) {
    const c = b.cells.find((x) => x.seat === seat)
    if (!c) continue
    const lx = c.x + drawing.cell / 2
    const ly = c.y + drawing.cell / 2
    const r = (b.rotation * Math.PI) / 180
    return { x: b.cx + lx * Math.cos(r) - ly * Math.sin(r), y: b.cy + lx * Math.sin(r) + ly * Math.cos(r) }
  }
  return null
}

export type Direction = 'left' | 'right' | 'up' | 'down'
const AXES: Record<Direction, [number, number]> = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }

/** The seat an arrow key moves to (issue #155): the closest one in that direction on screen,
 *  where a seat straight ahead beats a nearer one off to the side. Rotated blocks work too,
 *  because it goes by where seats are on the plan, not by rows. */
export function nextSeat(drawing: PlanDrawing, from: string, dir: Direction): string | null {
  const at = seatCenter(drawing, from)
  if (!at) return null
  const [ax, ay] = AXES[dir]
  let best: string | null = null
  let bestCost = Infinity
  for (const b of drawing.shapes) {
    for (const c of b.cells) {
      if (c.seat === from) continue
      const p = seatCenter(drawing, c.seat)!
      const dx = p.x - at.x
      const dy = p.y - at.y
      const ahead = dx * ax + dy * ay
      const side = Math.abs(dx * ay - dy * ax)
      // Within 45 degrees of the arrow, and not just a rounding step sideways.
      if (ahead < drawing.cell * 0.3 || side > ahead) continue
      const cost = ahead + side * 3
      if (cost < bestCost) { bestCost = cost; best = c.seat }
    }
  }
  return best
}

/** The seat closest to a point, for the first arrow press. */
export function nearestSeat(drawing: PlanDrawing, point: { x: number; y: number }): string | null {
  let best: string | null = null
  let bestD = Infinity
  for (const b of drawing.shapes) {
    for (const c of b.cells) {
      const p = seatCenter(drawing, c.seat)!
      const d = Math.hypot(p.x - point.x, p.y - point.y)
      if (d < bestD) { bestD = d; best = c.seat }
    }
  }
  return best
}

/** The same view while `point` is well inside it, else the view centred on it along the axis it
 *  left, so the keyboard cursor never sits at the edge. */
export function reveal(view: View, point: { x: number; y: number }, margin: number): View {
  const m = Math.min(margin, view.w / 4, view.h / 4)
  let { x, y } = view
  if (point.x < x + m || point.x > x + view.w - m) x = point.x - view.w / 2
  if (point.y < y + m || point.y > y + view.h - m) y = point.y - view.h / 2
  return x === view.x && y === view.y ? view : { ...view, x, y }
}

export type Filter = 'all' | 'problems' | 'offline' | 'recent' | 'match' | 'checked_in'

export function matches(seat: PlanSeat | undefined, filter: Filter) {
  if (filter === 'all') return true
  if (!seat) return false
  if (filter === 'problems') return !!seat.problems
  if (filter === 'offline') return seat.state === 'offline'
  if (filter === 'match') return !!seat.match
  if (filter === 'recent') return !!seat.changed
  return !!seat.checked_in
}

/** Seats in reading order: by block, then by number (D-2 before D-10). */
export function seatOrder(a: string, b: string) {
  const [ba, na] = [a.replace(/-?\d+$/, ''), Number(a.match(/(\d+)$/)?.[1] ?? 0)]
  const [bb, nb] = [b.replace(/-?\d+$/, ''), Number(b.match(/(\d+)$/)?.[1] ?? 0)]
  return ba.localeCompare(bb) || na - nb
}

/** "D-6" from "d6", "d 6" or "D-06", if the plan has it. */
export function findSeat(query: string, seats: Record<string, unknown>) {
  const q = query.trim().toUpperCase().replace(/\s+/g, '')
  if (!q) return null
  if (q in seats) return q
  const m = q.match(/^([A-Z0-9]+?)-?0*(\d+)$/)
  if (m && `${m[1]}-${m[2]}` in seats) return `${m[1]}-${m[2]}`
  return null
}

/** Whole minutes since a time in seconds, for "changed 4 min ago". */
export function minutesAgo(ts: number, now = Date.now() / 1000) {
  return Math.max(0, Math.round((now - ts) / 60))
}

/** Bits per second as a short text: 6 Mbit/s. */
export function rate(bps: number) {
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbit/s`
  if (bps >= 1e6) return `${Math.round(bps / 1e6)} Mbit/s`
  if (bps >= 1e3) return `${Math.round(bps / 1e3)} kbit/s`
  return `${bps} bit/s`
}

// Traffic overlay (issue #152): a fixed log scale, so the same colour means the same traffic in
// every hall and at every hour, and viridis, which stays in order for colour-blind eyes and in
// grey scale (the editor's rainbow heatmap does not).
export const HEAT_MIN = 1e5
export const HEAT_MAX = 1e9
const VIRIDIS: [number, number, number][] = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]]

export function heatLevel(bps: number | undefined) {
  if (!bps || bps <= HEAT_MIN) return 0
  return Math.min(1, Math.log10(bps / HEAT_MIN) / Math.log10(HEAT_MAX / HEAT_MIN))
}

export function heatColor(level: number) {
  const x = Math.min(1, Math.max(0, level)) * (VIRIDIS.length - 1)
  const i = Math.min(VIRIDIS.length - 2, Math.floor(x))
  const f = x - i
  const c = VIRIDIS[i].map((v, k) => Math.round(v + (VIRIDIS[i + 1][k] - v) * f))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

export const HEAT_GRADIENT = `linear-gradient(90deg, ${VIRIDIS.map((c) => `rgb(${c.join(', ')})`).join(', ')})`

export interface LinkSpan { from: number; to: number; on: boolean | null }

/** The seat's link history as spans from `from` to `to` (issue #167). */
export function linkSpans(h: { from: number; to: number; start: boolean | null; changes: [number, number][] }): LinkSpan[] {
  const out: LinkSpan[] = []
  let at = h.from
  let on: boolean | null = h.start
  for (const [t, v] of h.changes) {
    if (t > at) out.push({ from: at, to: Math.min(t, h.to), on })
    at = Math.max(at, t)
    on = !!v
  }
  if (h.to > at) out.push({ from: at, to: h.to, on })
  return out
}
