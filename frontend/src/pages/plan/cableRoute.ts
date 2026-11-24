import type { PlanCable, PlanCell, PlanDrawing, PlanShape, SeatViewData } from '@/api/types'
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
    const farHalf = sy < box.cy ? seat[1] > box.cy : seat[1] < box.cy
    if (box.sideways || !farHalf) return [[sx, near], [seat[0], near]]
    const x = sx < box.cx ? box.l - (TRUNK * PITCH_X) / 2 : box.r + (TRUNK * PITCH_X) / 2
    return [[sx, near], [x, near], [x, far], [seat[0], far]]
  }
  const x = sx < box.cx ? box.l - (TRUNK * PITCH_X) / 2 : box.r + (TRUNK * PITCH_X) / 2
  return [[x, sy], [x, seat[1]]]
}

/** The route into a seat whose row has a lane, as the server draws it (cable_plan._in_lane): to the
 *  block's end nearer the start, along it to the lane, along the lane to the seat. In the block's
 *  own frame (drawing units), so a turned block's cables turn with it. */
export function inLane(start: Pt, shape: PlanShape, c: PlanCell, cell: number, size: Size): Pt[] {
  const a = (shape.rotation * Math.PI) / 180, cos = Math.cos(a), sin = Math.sin(a)
  const dx = (start[0] / 100) * size.w - shape.cx, dy = (start[1] / 100) * size.h - shape.cy
  const su = dx * cos + dy * sin, sv = -dx * sin + dy * cos
  const w = shape.w / 2, h = shape.h / 2, out = (TRUNK * cell) / 2
  const u = c.x + cell / 2, lane = c.y + cell / 2 + (c.lane ?? 0)
  const end = su < 0 ? -w - out : w + out
  const bends: Pt[] = -w <= su && su <= w
    ? [[su, sv < 0 ? -h - out : h + out], [end, sv < 0 ? -h - out : h + out], [end, lane], [u, lane]]
    : [[end, sv], [end, lane], [u, lane]]
  return bends.map(([bu, bv]) => pct(size, shape.cx + bu * cos - bv * sin, shape.cy + bu * sin + bv * cos))
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
  const shapeOf = (seat: string) => drawing.shapes.find((b) => b.cells.some((c) => c.seat === seat))
  const blockOf = (shape: PlanShape | undefined) => {
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
    if (c.corners === 'straight') return { ...c, points: [start, end] }
    // Through a patch panel the panel's leg stays as drawn; the rest follows the seat.
    if (c.manual || c.via) return { ...c, points: [start, ...c.points.slice(1, -1), end] }
    const shape = shapeOf(c.ref.seat), seatCell = shape?.cells.find((x) => x.seat === c.ref.seat)
    const bends = shape && seatCell?.lane != null ? inLane(start, shape, seatCell, drawing.cell, size) : toSeat(start, end, blockOf(shape))
    return { ...c, points: tidy([start, ...bends, end]) }
  })
}

/** A bundle on the plan (drawing units): the stretch where its count shows, and how many cables run there. */
export interface Bundle { x1: number; y1: number; x2: number; y2: number; count: number }

interface Seg { cable: number; i: number; lo: number; hi: number; exit: number; len: number }

/** Seat cables that share a run drawn side by side, like a ribbon, instead of on top of each other
 *  (Mike, issue #1342: "it should still be visible that there are multiple cables"). Each cable
 *  keeps its own thin line, so one can be followed out to its seat; the ribbon narrows as cables
 *  leave it. Cables that turn off first run on the side they turn to, so they peel off without
 *  crossing the others. The last stretch, into the seat, stays where it is, so the plug does too.
 *
 *  Returns the cables with their points moved (still in % of the plan) and one ``Bundle`` per run of
 *  two or more cables, on its fullest stretch, for the count. Only straight runs across or down
 *  count; ``cell`` (drawing units) sets how far apart the cables run. */
export function spread(cables: PlanCable[], size: Size, cell = 32): { cables: PlanCable[]; bundles: Bundle[] } {
  const pts = cables.map((c) => c.points.map(([x, y]): Pt => [round((x / 100) * size.w), round((y / 100) * size.h)]))
  const lines = new Map<string, Seg[]>()
  cables.forEach((c, k) => {
    if (c.kind !== 'lan' || c.corners === 'straight') return
    const p = pts[k]
    // Not the last stretch: the drop into the seat stays put.
    for (let i = 0; i < p.length - 2; i++) {
      const [a, b, next] = [p[i], p[i + 1], p[i + 2]]
      const across = Math.abs(a[1] - b[1]) < 0.5, down = Math.abs(a[0] - b[0]) < 0.5
      if (across === down) continue
      const key = across ? `h${Math.round(a[1])}` : `v${Math.round(a[0])}`
      const [from, to] = across ? [a[0], b[0]] : [a[1], b[1]]
      const turn = across ? next[1] - b[1] : next[0] - b[0]
      if (!lines.has(key)) lines.set(key, [])
      lines.get(key)!.push({ cable: k, i, lo: Math.min(from, to), hi: Math.max(from, to), exit: Math.abs(turn) < 0.5 ? 0 : Math.sign(turn), len: Math.abs(to - from) })
    }
  })
  const offsets = cables.map((c) => new Array<number>(Math.max(0, c.points.length - 1)).fill(0))
  const out: Bundle[] = []
  for (const [key, segs] of lines) {
    const across = key[0] === 'h', at = Number(key.slice(1))
    // Runs that overlap on this line are one bundle.
    segs.sort((a, b) => a.lo - b.lo)
    const groups: Seg[][] = []
    for (const s of segs) {
      const g = groups[groups.length - 1]
      if (g && s.lo < Math.max(...g.map((x) => x.hi)) - 0.5) g.push(s)
      else groups.push([s])
    }
    for (const g of groups) {
      if (new Set(g.map((s) => s.cable)).size < 2) continue
      // A cable turning down (or right) runs on that side, the soonest to leave outermost.
      const score = (s: Seg) => (s.exit > 0 ? 2e6 - s.len : s.exit < 0 ? -2e6 + s.len : 0)
      const order = [...g].sort((a, b) => score(a) - score(b) || a.cable - b.cable)
      const gap = Math.min(cell * 0.09, (cell * 0.6) / (order.length - 1))
      order.forEach((s, slot) => { offsets[s.cable][s.i] = (slot - (order.length - 1) / 2) * gap })
      const label = fullest(g)
      out.push(across ? { x1: label[0], y1: at, x2: label[1], y2: at, count: label[2] } : { x1: at, y1: label[0], x2: at, y2: label[1], count: label[2] })
    }
  }
  const moved = cables.map((c, k) => {
    const p = pts[k], off = offsets[k]
    if (!off.some((o) => o)) return c
    // Each bend moves across by the run before it and the run after it, so the corners stay square.
    const axis = (i: number) => (Math.abs(p[i][1] - p[i + 1][1]) < 0.5 ? 'h' : Math.abs(p[i][0] - p[i + 1][0]) < 0.5 ? 'v' : '')
    const shifted = p.map((q, j): Pt => {
      let [x, y] = q
      for (const i of [j - 1, j]) {
        if (i < 0 || i >= off.length || !off[i]) continue
        if (axis(i) === 'h') y = q[1] + off[i]
        else if (axis(i) === 'v') x = q[0] + off[i]
      }
      return [x, y]
    })
    // Both ends stay where they are: the cable leaves its switch and meets its seat as before.
    const points = [p[0], ...shifted.slice(0, -1), p[p.length - 1]]
      .filter((q, j, all) => j === 0 || !same(q, all[j - 1]))
      .map(([x, y]): Pt => [(x / size.w) * 100, (y / size.h) * 100])
    return { ...c, points }
  })
  return { cables: moved, bundles: out }
}

/** The fullest stretch of one bundle (the longest when two are as full): ``[from, to, count]``. */
function fullest(segs: Seg[]): [number, number, number] {
  const edges = segs.flatMap((s): [number, number][] => [[s.lo, 1], [s.hi, -1]]).sort((p, q) => p[0] - q[0] || q[1] - p[1])
  let count = 0, at = edges[0][0]
  let best: [number, number, number] = [at, at, 0]
  for (const [pos, step] of edges) {
    if (pos > at && (count > best[2] || (count === best[2] && pos - at > best[1] - best[0]))) best = [at, pos, count]
    count += step
    at = pos
  }
  return best
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
