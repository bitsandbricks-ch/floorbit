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

export type Filter = 'all' | 'problems' | 'offline' | 'match' | 'checked_in'

export function matches(seat: PlanSeat | undefined, filter: Filter) {
  if (filter === 'all') return true
  if (!seat) return false
  if (filter === 'problems') return !!seat.problems
  if (filter === 'offline') return seat.state === 'offline'
  if (filter === 'match') return !!seat.match
  return !!seat.checked_in
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
