import type { PlanShape } from '@/api/types'
import { type BlockRow, defaultSides } from './rows'

/** A point in seats. */
export type Pt = [number, number]

export const BEND_MAX = 330, POINTS_MAX = 50

// ── The row's seats in its own frame, as floorbit/seat_rows.py lays them out ──────────────

function along(row: BlockRow): { at: number[]; length: number } {
  const extra = new Map<number, number>()
  for (const g of row.col_gaps ?? []) extra.set(Math.round(g.after), (extra.get(Math.round(g.after)) ?? 0) + Number(g.size))
  const at: number[] = []
  let d = 0
  for (let i = 0; i < row.seats; i++) {
    at.push(d + 0.5)
    d += 1 + (i < row.seats - 1 ? extra.get(i + 1) ?? 0 : 0)
  }
  return { at, length: d }
}

/** A point ``d`` seats along a path, carrying on along the last leg past its end. */
export function pointAlong(path: Pt[], d: number): Pt {
  const legs = path.slice(1).map((q, i) => [path[i], q, Math.hypot(q[0] - path[i][0], q[1] - path[i][1])] as const).filter((l) => l[2] > 0)
  if (!legs.length) return path[0] ?? [0, 0]
  let walked = 0
  for (let i = 0; i < legs.length; i++) {
    const [p, q, n] = legs[i]
    if (d <= walked + n || i === legs.length - 1) {
      const t = (d - walked) / n
      return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]
    }
    walked += n
  }
  return path[path.length - 1]
}

/** Each seat's centre in the row's own frame (any origin), in seat order. */
export function rowSeats(row: BlockRow): Pt[] {
  const { at, length } = along(row)
  if (row.shape === 'arc' && Math.abs(row.bend ?? 0) >= 0.06) {
    const turn = ((row.bend ?? 0) * Math.PI) / 180, radius = length / turn, start = -turn / 2
    return at.map((d) => { const phi = start + d / radius; return [radius * (Math.sin(phi) - Math.sin(start)), -radius * (Math.cos(phi) - Math.cos(start))] })
  }
  if (row.shape === 'u') {
    const [a, b, c] = row.sides ?? defaultSides('u', row.seats)!
    const deep = Math.max(a, c), right = (a ? 1.5 : 0.5) + b
    return [
      ...Array.from({ length: a }, (_, i): Pt => [0.5, deep - a + i + 0.5]),
      ...Array.from({ length: b }, (_, i): Pt => [a ? 1.5 + i : 0.5 + i, deep + 0.5]),
      ...Array.from({ length: c }, (_, i): Pt => [right, deep - i - 0.5]),
    ]
  }
  if (row.shape === 'l') {
    const [a, b] = row.sides ?? defaultSides('l', row.seats)!
    return [
      ...Array.from({ length: a }, (_, i): Pt => [0.5, i + 0.5]),
      ...Array.from({ length: b }, (_, i): Pt => [a ? 1.5 + i : 0.5 + i, a + 0.5]),
    ]
  }
  if (row.shape === 'path') {
    const path = row.path?.length ? row.path : [[0, 0], [row.seats, 0]] as Pt[]
    return at.map((d) => pointAlong(path, d))
  }
  return at.map((d): Pt => [d, 0.5])
}

// ── From the drawn block ───────────────────────────────────────────────────────────────

/** Row ``r``'s seat centres as drawn, in seats from the block's top-left, in seat order. */
export function drawnSeats(shape: PlanShape, cell: number, r: number): Pt[] {
  return shape.cells.filter((c) => c.rc?.[0] === r).sort((a, b) => a.rc![1] - b.rc![1])
    .map((c): Pt => [(c.x + shape.w / 2) / cell + 0.5, (c.y + shape.h / 2) / cell + 0.5])
}

/** How far the row's own frame sits from the block's: add it to a row point to get a block point. */
export function rowOffset(row: BlockRow, drawn: Pt[]): Pt {
  const own = rowSeats(row)[0], seat = drawn[0]
  return own && seat ? [seat[0] - own[0], seat[1] - own[1]] : [0, 0]
}

// ── Changing the shape ─────────────────────────────────────────────────────────────────

/** The bend (degrees) that puts the middle of an arc through ``p``: from how far ``p`` stands off
 *  the line from the first seat to the last. Positive bows to the left of the way the row runs. */
export function bendThrough(first: Pt, last: Pt, p: Pt, free = false): number {
  const dx = last[0] - first[0], dy = last[1] - first[1], chord = Math.hypot(dx, dy)
  if (chord < 0.01) return 0
  const mid: Pt = [(first[0] + last[0]) / 2, (first[1] + last[1]) / 2]
  const off = ((p[0] - mid[0]) * dy - (p[1] - mid[1]) * dx) / chord
  const deg = (4 * Math.atan((2 * off) / chord) * 180) / Math.PI
  const v = Math.max(-BEND_MAX, Math.min(BEND_MAX, deg))
  return free ? Math.round(v) : Math.round(v / 5) * 5
}

/** A U's or L's ``arm`` made ``by`` seats longer; the middle (U) or the other arm (L) gives or takes
 *  the seats, so the row keeps its count. */
export function withArm(row: BlockRow, arm: number, by: number): BlockRow {
  const sides = [...(row.sides ?? defaultSides(row.shape, row.seats) ?? [])]
  if (!sides.length || arm >= sides.length) return row
  const other = row.shape === 'u' ? 1 : 1 - arm
  const move = Math.max(-sides[arm], Math.min(sides[other], Math.round(by)))
  sides[arm] += move
  sides[other] -= move
  return { ...row, sides }
}

/** Where an arm can be dragged: the arm's outer seat, and the way it grows (row frame). */
export function armEnds(row: BlockRow): { arm: number; at: Pt; grow: Pt }[] {
  const seats = rowSeats(row)
  const sides = row.sides ?? defaultSides(row.shape, row.seats) ?? []
  if (row.shape === 'u') {
    const out = []
    if (sides[0]) out.push({ arm: 0, at: seats[0], grow: [0, -1] as Pt })
    if (sides[2]) out.push({ arm: 2, at: seats[seats.length - 1], grow: [0, -1] as Pt })
    return out
  }
  if (row.shape === 'l') {
    const out = []
    if (sides[0]) out.push({ arm: 0, at: seats[0], grow: [0, -1] as Pt })
    if (sides[1]) out.push({ arm: 1, at: seats[seats.length - 1], grow: [1, 0] as Pt })
    return out
  }
  return []
}

/** The path with point ``i`` at ``p``, on quarter seats unless placed freely. */
export function movePoint(path: Pt[], i: number, p: Pt, free = false): Pt[] {
  const snap = (v: number) => (free ? Math.round(v * 100) / 100 : Math.round(v * 4) / 4)
  return path.map((q, k) => (k === i ? [snap(p[0]), snap(p[1])] : q))
}

/** A new point halfway along leg ``i`` (between points i and i + 1). */
export function addPoint(path: Pt[], i: number): Pt[] {
  if (path.length >= POINTS_MAX || i < 0 || i >= path.length - 1) return path
  const [p, q] = [path[i], path[i + 1]]
  const mid: Pt = [Math.round(((p[0] + q[0]) / 2) * 100) / 100, Math.round(((p[1] + q[1]) / 2) * 100) / 100]
  return [...path.slice(0, i + 1), mid, ...path.slice(i + 1)]
}

/** The path without point ``i``; a path keeps at least two. */
export function dropPoint(path: Pt[], i: number): Pt[] {
  return path.length <= 2 ? path : path.filter((_, k) => k !== i)
}

// ── Keeping the block in place ─────────────────────────────────────────────────────────

/** Every seat's centre in the block's own frame, the box starting at 0,0, as
 *  floorbit/seat_rows.py ``layout`` has it: ``at[r][c]``. */
export function blockSeats(rows: BlockRow[]): { at: Pt[][]; w: number; h: number } {
  const laid = rows.map((row) => {
    const seats = rowSeats(row)
    const xs = seats.map((p) => p[0]), ys = seats.map((p) => p[1])
    const left = Math.min(...xs) - 0.5, top = Math.min(...ys) - 0.5
    return { row, seats: seats.map((p): Pt => [p[0] - left, p[1] - top]), w: Math.max(...xs) + 0.5 - left, h: Math.max(...ys) + 0.5 - top }
  })
  const widest = Math.max(0, ...laid.map((l) => l.w))
  let y = 0
  const at = laid.map((l, r) => {
    if (r) y += Number(l.row.gap) || 0
    const x = (l.row.align === 'middle' ? (widest - l.w) / 2 : l.row.align === 'end' ? widest - l.w : 0) + (Number(l.row.shift) || 0)
    const out = l.seats.map((p): Pt => [p[0] + x, p[1] + y])
    y += l.h
    return out
  })
  const all = at.flat()
  if (!all.length) return { at, w: 0, h: 0 }
  const left = Math.min(...all.map((p) => p[0])) - 0.5, top = Math.min(...all.map((p) => p[1])) - 0.5
  const moved = at.map((row) => row.map((p): Pt => [p[0] - left, p[1] - top]))
  return { at: moved, w: Math.max(...all.map((p) => p[0])) + 0.5 - left, h: Math.max(...all.map((p) => p[1])) + 0.5 - top }
}

/** The seat that stays put while row ``row`` changes: a U's middle, an L's corner, else the first
 *  seat (the last when the path's first point moves). */
export function anchorSeat(row: BlockRow, firstPointMoves = false): number {
  const sides = row.sides ?? defaultSides(row.shape, row.seats) ?? []
  if (row.shape === 'u' || row.shape === 'l') return Math.min(row.seats - 1, sides[0] ?? 0)
  return firstPointMoves ? row.seats - 1 : 0
}

/** Row ``r`` changed from ``rows[r]`` to ``next``: where the block's seats go, in the block's frame as
 *  drawn now (``seats[c]`` for the changed row), and its new x/y in % of a plan ``size`` units big,
 *  so the anchor seat stays where it is on the plan. */
export function reshaped(shape: PlanShape, cell: number, size: { w: number; h: number }, rows: BlockRow[], r: number, next: BlockRow, firstPointMoves = false) {
  const now = blockSeats(rows.map((x, k) => (k === r ? next : x)))
  const was = drawnSeats(shape, cell, r)
  const a = was[Math.min(was.length - 1, anchorSeat(rows[r], firstPointMoves))] ?? [0, 0]
  const b = now.at[r]?.[Math.min(next.seats - 1, anchorSeat(next, firstPointMoves))] ?? [0, 0]
  // The new layout drawn so the anchor seat lies on its old place.
  const seats = (now.at[r] ?? []).map((p): Pt => [p[0] - b[0] + a[0], p[1] - b[1] + a[1]])
  // From the block's middle, before and after: the middle moves by the difference, turned with the block.
  const dx = (a[0] - shape.w / cell / 2 - (b[0] - now.w / 2)) * cell, dy = (a[1] - shape.h / cell / 2 - (b[1] - now.h / 2)) * cell
  const t = (shape.rotation * Math.PI) / 180
  const cx = shape.cx + dx * Math.cos(t) - dy * Math.sin(t), cy = shape.cy + dx * Math.sin(t) + dy * Math.cos(t)
  return { seats, x: Math.round((cx / size.w) * 100000) / 1000, y: Math.round((cy / size.h) * 100000) / 1000 }
}
