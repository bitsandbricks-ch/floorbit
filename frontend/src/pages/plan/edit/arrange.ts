import type { SeatViewData } from '@/api/types'
import { type Box, type ItemRef, type Point, outlineOf, refKey, sameRef } from './geometry'

/** The axis-aligned box an item takes on the plan (its outline turned with it), in drawing units. */
export function boundsOf(data: SeatViewData, ref: ItemRef): Box | null {
  const o = outlineOf(data, ref)
  if (!o) return null
  if (!o.rotation) return o.box
  const r = (o.rotation * Math.PI) / 180
  const { x, y, w, h } = o.box
  const corners = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].map(([px, py]) => {
    const dx = px - o.centre.x, dy = py - o.centre.y
    return [o.centre.x + dx * Math.cos(r) - dy * Math.sin(r), o.centre.y + dx * Math.sin(r) + dy * Math.cos(r)]
  })
  const xs = corners.map((c) => c[0]), ys = corners.map((c) => c[1])
  return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
}

function union(boxes: Box[]): Box | null {
  if (!boxes.length) return null
  const l = Math.min(...boxes.map((b) => b.x)), t = Math.min(...boxes.map((b) => b.y))
  const r = Math.max(...boxes.map((b) => b.x + b.w)), b = Math.max(...boxes.map((b2) => b2.y + b2.h))
  return { x: l, y: t, w: r - l, h: b - t }
}

const groupOfBlock = (data: SeatViewData, ref: ItemRef) =>
  ref.kind === 'block' ? data.drawing?.shapes.find((s) => s.id === ref.id)?.group ?? null : null

/** ``refs`` with every block of their groups added: a group is picked as one. */
export function withGroups(data: SeatViewData, refs: ItemRef[]): ItemRef[] {
  const groups = new Set(refs.map((r) => groupOfBlock(data, r)).filter(Boolean))
  if (!groups.size) return refs
  const more = (data.drawing?.shapes ?? []).filter((s) => s.id && s.group && groups.has(s.group))
    .map((s) => ({ kind: 'block' as const, id: s.id! }))
  return [...refs, ...more.filter((m) => !refs.some((r) => sameRef(r, m)))]
}

export type AlignHow = 'left' | 'hcenter' | 'right' | 'top' | 'vcenter' | 'bottom'

/** Moves that line ``refs`` up on the selection's edge or middle (each item as a whole). */
export function alignMoves(data: SeatViewData, refs: ItemRef[], how: AlignHow): [ItemRef, Point][] {
  const items = refs.map((r) => [r, boundsOf(data, r)] as const).filter((x): x is readonly [ItemRef, Box] => !!x[1])
  const all = union(items.map(([, b]) => b))
  if (!all || items.length < 2) return []
  return items.map(([r, b]) => {
    const d = { x: 0, y: 0 }
    if (how === 'left') d.x = all.x - b.x
    if (how === 'right') d.x = all.x + all.w - (b.x + b.w)
    if (how === 'hcenter') d.x = all.x + all.w / 2 - (b.x + b.w / 2)
    if (how === 'top') d.y = all.y - b.y
    if (how === 'bottom') d.y = all.y + all.h - (b.y + b.h)
    if (how === 'vcenter') d.y = all.y + all.h / 2 - (b.y + b.h / 2)
    return [r, d] as [ItemRef, Point]
  }).filter(([, d]) => Math.abs(d.x) > 0.01 || Math.abs(d.y) > 0.01)
}

/** Moves that leave the same gap between ``refs`` along one axis; the first and last stay. */
export function distributeMoves(data: SeatViewData, refs: ItemRef[], axis: 'x' | 'y'): [ItemRef, Point][] {
  const items = refs.map((r) => [r, boundsOf(data, r)] as const).filter((x): x is readonly [ItemRef, Box] => !!x[1])
  if (items.length < 3) return []
  const size = (b: Box) => (axis === 'x' ? b.w : b.h)
  const start = (b: Box) => (axis === 'x' ? b.x : b.y)
  const sorted = [...items].sort((a, b) => start(a[1]) - start(b[1]))
  const first = sorted[0][1], last = sorted[sorted.length - 1][1]
  const span = start(last) + size(last) - start(first)
  const gap = (span - sorted.reduce((s, [, b]) => s + size(b), 0)) / (sorted.length - 1)
  let at = start(first)
  const out: [ItemRef, Point][] = []
  for (const [r, b] of sorted) {
    const move = at - start(b)
    if (Math.abs(move) > 0.01) out.push([r, axis === 'x' ? { x: move, y: 0 } : { x: 0, y: move }])
    at += size(b) + gap
  }
  return out
}

export interface Guide { axis: 'x' | 'y'; at: number }

/** While dragging ``moving`` by ``d``: the move that puts an edge or middle of the moving items on
 *  one of another item's (within ``reach`` drawing units), and the lines that show why. */
export function snapToGuides(data: SeatViewData, moving: ItemRef[], d: Point, reach: number, others: ItemRef[]): { d: Point; guides: Guide[] } {
  const box = union(moving.map((r) => boundsOf(data, r)).filter((b): b is Box => !!b))
  if (!box) return { d, guides: [] }
  const keys = new Set(moving.map(refKey))
  const targets = others.filter((r) => !keys.has(refKey(r))).map((r) => boundsOf(data, r)).filter((b): b is Box => !!b)
  const lines = (b: Box, axis: 'x' | 'y') => (axis === 'x' ? [b.x, b.x + b.w / 2, b.x + b.w] : [b.y, b.y + b.h / 2, b.y + b.h])
  const out = { ...d }
  const guides: Guide[] = []
  for (const axis of ['x', 'y'] as const) {
    const mine = lines(box, axis).map((v) => v + d[axis])
    let best: { diff: number; at: number } | null = null
    for (const t of targets) {
      for (const at of lines(t, axis)) {
        for (const m of mine) {
          const diff = at - m
          if (Math.abs(diff) <= reach && (!best || Math.abs(diff) < Math.abs(best.diff))) best = { diff, at }
        }
      }
    }
    if (best) { out[axis] = d[axis] + best.diff; guides.push({ axis, at: best.at }) }
  }
  return { d: out, guides }
}
