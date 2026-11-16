import type { PlanMark, PlanShape, SeatViewData } from '@/api/types'

/** What the editor can select on the plan. Ids are the server's: seat block, plan mark, switch,
 *  patch panel (its name) and cable (crew and imported cables; ones only the port watch read have none). */
export type ItemKind = 'block' | 'mark' | 'switch' | 'panel' | 'cable' | 'board'
export interface ItemRef { kind: ItemKind; id: string }
export const refKey = (r: ItemRef) => `${r.kind}:${r.id}`
export const sameRef = (a: ItemRef, b: ItemRef) => a.kind === b.kind && a.id === b.id

export interface Point { x: number; y: number }
export interface Box { x: number; y: number; w: number; h: number }

/** The plan's size in drawing units (``data.size``) maps to 0..100 % on both axes, as the server
 *  stores positions (floorbit/blueprints/screen.py PLAN_W, PLAN_H). */
export const toPct = (size: { w: number; h: number }, p: Point): Point => ({ x: (p.x / size.w) * 100, y: (p.y / size.h) * 100 })
export const fromPct = (size: { w: number; h: number }, p: Point): Point => ({ x: (p.x / 100) * size.w, y: (p.y / 100) * size.h })

/** The editor's grid step in % (static/js/editor: 0.5 %), so both editors put things on the same lines. */
export const SNAP_PCT = 0.5
export const snapPct = (v: number, step = SNAP_PCT) => Math.round(v / step) * step
const round2 = (v: number) => Math.round(v * 100) / 100

/** Where an item sits, in drawing units: a block's centre, a mark's anchor, a switch. */
export function anchorOf(data: SeatViewData, ref: ItemRef): Point | null {
  if (ref.kind === 'block') {
    const s = data.drawing?.shapes.find((b) => b.id === ref.id)
    return s ? { x: s.cx, y: s.cy } : null
  }
  if (ref.kind === 'mark') {
    const m = data.drawing?.marks?.find((x) => x.id === ref.id)
    return m ? { x: m.x, y: m.y } : null
  }
  if (ref.kind === 'panel') {
    const p = data.panels?.find((x) => x.name === ref.id)
    return p ? { x: p.x, y: p.y } : null
  }
  if (ref.kind === 'board') {
    const b = data.boards?.find((x) => x.id === ref.id)
    return b ? { x: b.x, y: b.y } : null
  }
  if (ref.kind === 'cable') return null
  const w = data.switches.find((x) => x.id === ref.id)
  return w ? { x: w.x, y: w.y } : null
}

/** The move to apply so the first item lands on the grid (with ``snap``), in drawing units. */
export function snappedDelta(data: SeatViewData, lead: ItemRef, raw: Point, snap: boolean): Point {
  const at = anchorOf(data, lead)
  if (!snap || !at) return raw
  const pct = toPct(data.size, { x: at.x + raw.x, y: at.y + raw.y })
  const to = fromPct(data.size, { x: snapPct(pct.x), y: snapPct(pct.y) })
  return { x: to.x - at.x, y: to.y - at.y }
}

const shift = <T extends Point>(p: T, d: Point): T => ({ ...p, x: p.x + d.x, y: p.y + d.y })
function shiftMark(m: PlanMark, d: Point): PlanMark {
  const out = shift(m, d)
  if (m.kind === 'wall' && m.x2 !== undefined && m.y2 !== undefined) return { ...out, x2: m.x2 + d.x, y2: m.y2 + d.y }
  return out
}

/** ``data`` with the selected items moved by ``d`` (drawing units): what the plan shows while dragging
 *  and until the server's answer comes back. */
export function moved(data: SeatViewData, items: ItemRef[], d: Point): SeatViewData {
  if (!items.length || (!d.x && !d.y) || !data.drawing) return data
  const has = (kind: ItemKind, id?: string) => !!id && items.some((r) => r.kind === kind && r.id === id)
  const shapes: PlanShape[] = data.drawing.shapes.map((s) => (has('block', s.id) ? { ...s, cx: s.cx + d.x, cy: s.cy + d.y } : s))
  const marks = data.drawing.marks?.map((m) => (has('mark', m.id) ? shiftMark(m, d) : m))
  const switches = data.switches.map((w) => (has('switch', w.id) ? shift(w, d) : w))
  const panels = data.panels?.map((p) => (has('panel', p.name) ? shift(p, d) : p))
  const boards = data.boards?.map((b) => (has('board', b.id) ? shift(b, d) : b))
  return { ...data, drawing: { ...data.drawing, shapes, marks }, switches, panels, boards }
}

/** The server update that puts one item where ``moved`` drew it, in % of the plan; the inverse is
 *  the same call with ``-d``. */
export function movePatch(data: SeatViewData, ref: ItemRef, d: Point): Record<string, number> | null {
  const pct = (p: Point) => { const v = toPct(data.size, p); return { x: round2(v.x), y: round2(v.y) } }
  if (ref.kind === 'block') {
    const s = data.drawing?.shapes.find((b) => b.id === ref.id)
    return s ? pct({ x: s.cx + d.x, y: s.cy + d.y }) : null
  }
  if (ref.kind === 'mark') {
    const m = data.drawing?.marks?.find((x) => x.id === ref.id)
    if (!m) return null
    const a = pct({ x: m.x + d.x, y: m.y + d.y })
    if (m.kind === 'wall' && m.x2 !== undefined && m.y2 !== undefined) {
      const b = pct({ x: m.x2 + d.x, y: m.y2 + d.y })
      return { ...a, x2: b.x, y2: b.y }
    }
    return a
  }
  if (ref.kind === 'cable') return null
  const at = anchorOf(data, ref)
  return at ? pct({ x: at.x + d.x, y: at.y + d.y }) : null
}

/** The outline the editor draws around a selected item, in drawing units (unrotated box and its rotation). */
export function outlineOf(data: SeatViewData, ref: ItemRef): { box: Box; rotation: number; centre: Point } | null {
  const cell = data.drawing?.cell ?? 32
  if (ref.kind === 'block') {
    const s = data.drawing?.shapes.find((b) => b.id === ref.id)
    if (!s) return null
    const pad = 6
    return { box: { x: s.cx - s.w / 2 - pad, y: s.cy - s.h / 2 - pad, w: s.w + 2 * pad, h: s.h + 2 * pad }, rotation: s.rotation, centre: { x: s.cx, y: s.cy } }
  }
  if (ref.kind === 'switch') {
    const w = data.switches.find((x) => x.id === ref.id)
    return w ? { box: { x: w.x - 12, y: w.y - 12, w: 24, h: 24 }, rotation: 0, centre: w } : null
  }
  if (ref.kind === 'panel') {
    const p = data.panels?.find((x) => x.name === ref.id)
    return p ? { box: { x: p.x - 20, y: p.y - 9, w: 40, h: 18 }, rotation: 0, centre: { x: p.x, y: p.y } } : null
  }
  if (ref.kind === 'board') {
    const b = data.boards?.find((x) => x.id === ref.id)
    return b ? { box: { x: b.x - 26, y: b.y - 17, w: 52, h: 34 }, rotation: 0, centre: { x: b.x, y: b.y } } : null
  }
  if (ref.kind === 'cable') return null
  const m = data.drawing?.marks?.find((x) => x.id === ref.id)
  if (!m) return null
  if (m.kind === 'zone') return { box: { x: m.x, y: m.y, w: m.w ?? 0, h: m.h ?? 0 }, rotation: 0, centre: { x: m.x + (m.w ?? 0) / 2, y: m.y + (m.h ?? 0) / 2 } }
  if (m.kind === 'wall') {
    const x2 = m.x2 ?? m.x, y2 = m.y2 ?? m.y
    const box = { x: Math.min(m.x, x2) - 6, y: Math.min(m.y, y2) - 6, w: Math.abs(x2 - m.x) + 12, h: Math.abs(y2 - m.y) + 12 }
    return { box, rotation: 0, centre: { x: (m.x + x2) / 2, y: (m.y + y2) / 2 } }
  }
  const r = m.kind === 'icon' ? cell * ({ s: 0.5, m: 0.75, l: 1.1 }[m.size ?? 'm']) : cell * 0.6
  const wide = m.kind === 'text' ? Math.max(r * 2, (m.text ?? '').length * cell * 0.36) : r * 2
  return { box: { x: m.x - wide / 2, y: m.y - r, w: wide, h: r * 2 }, rotation: m.rotation ?? 0, centre: { x: m.x, y: m.y } }
}

/** Every selectable item on the plan, top-most last (switches over blocks over marks, as drawn). */
export function allItems(data: SeatViewData): ItemRef[] {
  const marks = (data.drawing?.marks ?? []).filter((m) => m.id).map((m) => ({ kind: 'mark' as const, id: m.id! }))
  const blocks = (data.drawing?.shapes ?? []).filter((s) => s.id).map((s) => ({ kind: 'block' as const, id: s.id! }))
  const panels = (data.panels ?? []).map((p) => ({ kind: 'panel' as const, id: p.name }))
  const boards = (data.boards ?? []).map((b) => ({ kind: 'board' as const, id: b.id }))
  const switches = data.switches.map((w) => ({ kind: 'switch' as const, id: w.id }))
  return [...marks, ...blocks, ...panels, ...boards, ...switches]
}

/** The items whose outline lies inside ``box`` (a drag on empty plan selects them). */
export function inside(data: SeatViewData, box: Box): ItemRef[] {
  return allItems(data).filter((r) => {
    const o = outlineOf(data, r)
    if (!o) return false
    return o.centre.x >= box.x && o.centre.x <= box.x + box.w && o.centre.y >= box.y && o.centre.y <= box.y + box.h
  })
}

export const boxFrom = (a: Point, b: Point): Box => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) })

/** The seat under ``p`` (drawing units), if any: each cell is ``cell`` square at its block-local
 *  corner, turned with the block. */
export function seatAt(data: SeatViewData, p: Point): string | null {
  const cell = data.drawing?.cell ?? 32
  for (const b of data.drawing?.shapes ?? []) {
    const r = (-b.rotation * Math.PI) / 180
    const dx = p.x - b.cx, dy = p.y - b.cy
    const lx = dx * Math.cos(r) - dy * Math.sin(r), ly = dx * Math.sin(r) + dy * Math.cos(r)
    const hit = b.cells.find((c) => lx >= c.x && lx < c.x + cell && ly >= c.y && ly < c.y + cell)
    if (hit) return hit.seat
  }
  return null
}

/** The switch or patch panel nearest to ``p`` within ``reach`` drawing units. */
export function nearest<T extends Point>(items: T[], p: Point, reach: number): T | null {
  let best: T | null = null, dist = reach
  for (const it of items) {
    const d = Math.hypot(it.x - p.x, it.y - p.y)
    if (d <= dist) { best = it; dist = d }
  }
  return best
}
