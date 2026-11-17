import { useRef, useState } from 'react'
import type { SeatViewData } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { type Box, type ItemRef, type Point, allItems, boxFrom, fromPct, inside, outlineOf, refKey, sameRef, snapPct, toPct } from './geometry'
import { TOOL_GESTURE, type Tool } from './tools'

/** The editor's layer over the plan: one hit area per item (switches on top, then blocks, then
 *  labels, walls and zones), the selection outlines, and a box to select by dragging on empty plan.
 *  Space + drag or the middle button pans, as in drawing tools; the plan below handles that. */
export function EditOverlay({ ctx, data, selection, onSelect, onDrag, onDrop, space, tool = 'select', onPlace, onLine, onBox }: {
  ctx: OverlayContext
  data: SeatViewData
  selection: ItemRef[]
  onSelect: (items: ItemRef[]) => void
  /** While dragging: the move so far, in drawing units, and whether to snap to the grid. */
  onDrag: (d: Point, snap: boolean, lead: ItemRef) => void
  onDrop: (d: Point, snap: boolean, lead: ItemRef) => void
  /** Space is held: let the plan pan. */
  space: boolean
  tool?: Tool
  /** A placing tool was clicked here (snapped unless Alt). */
  onPlace?: (at: Point) => void
  /** A line was drawn (the wall tool). */
  onLine?: (a: Point, b: Point) => void
  /** A box was drawn (the zone tool). */
  onBox?: (box: Box) => void
}) {
  const gesture = TOOL_GESTURE[tool]
  const [draft, setDraft] = useState<{ a: Point; b: Point } | null>(null)
  const snap = (p: Point, free: boolean, angle = false, from?: Point): Point => {
    if (angle && from) {
      // Shift: the line keeps to 15 degree steps from where it started.
      const dx = p.x - from.x, dy = p.y - from.y
      const len = Math.hypot(dx, dy)
      const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 12)) * (Math.PI / 12)
      return { x: from.x + Math.cos(a) * len, y: from.y + Math.sin(a) * len }
    }
    if (free) return p
    const pct = toPct(data.size, p)
    return fromPct(data.size, { x: snapPct(pct.x), y: snapPct(pct.y) })
  }
  const drag = useRef<{ start: Point; lead: ItemRef | null; moved: boolean; additive: boolean; id: number } | null>(null)
  const [marquee, setMarquee] = useState<Box | null>(null)
  const px = 1 / ctx.scale   // one screen pixel in drawing units

  const passes = (e: React.PointerEvent) => space || e.button === 1
  const begin = (e: React.PointerEvent, ref: ItemRef | null) => {
    if (passes(e) || e.button === 2) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    if (gesture !== 'select') {
      const at = snap(ctx.toPlan(e.clientX, e.clientY), e.altKey)
      if (gesture === 'click') onPlace?.(at)
      else setDraft({ a: at, b: at })
      return
    }
    const additive = e.shiftKey || e.metaKey || e.ctrlKey
    if (ref) {
      const picked = selection.some((r) => sameRef(r, ref))
      if (additive) onSelect(picked ? selection.filter((r) => !sameRef(r, ref)) : [...selection, ref])
      else if (!picked) onSelect([ref])
    }
    drag.current = { start: ctx.toPlan(e.clientX, e.clientY), lead: ref, moved: false, additive, id: e.pointerId }
  }
  const move = (e: React.PointerEvent) => {
    if (draft) {
      e.stopPropagation()
      setDraft({ a: draft.a, b: snap(ctx.toPlan(e.clientX, e.clientY), e.altKey, gesture === 'line' && e.shiftKey, draft.a) })
      return
    }
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    const at = ctx.toPlan(e.clientX, e.clientY)
    const delta = { x: at.x - d.start.x, y: at.y - d.start.y }
    if (!d.moved && Math.hypot(delta.x, delta.y) < 3 * px) return
    d.moved = true
    if (d.lead) {
      // An item picked with Shift that is no longer selected doesn't move anything.
      if (selection.some((r) => sameRef(r, d.lead!))) onDrag(delta, !e.altKey, d.lead)
    } else setMarquee(boxFrom(d.start, at))
  }
  const end = (e: React.PointerEvent) => {
    if (draft) {
      e.stopPropagation()
      setDraft(null)
      const tiny = Math.hypot(draft.b.x - draft.a.x, draft.b.y - draft.a.y) < 4 * px
      if (tiny) return
      if (gesture === 'line') onLine?.(draft.a, draft.b)
      else onBox?.(boxFrom(draft.a, draft.b))
      return
    }
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    const at = ctx.toPlan(e.clientX, e.clientY)
    if (d.lead) {
      if (d.moved && selection.some((r) => sameRef(r, d.lead!))) onDrop({ x: at.x - d.start.x, y: at.y - d.start.y }, !e.altKey, d.lead)
      else if (!d.moved && !d.additive) onSelect([d.lead])
      return
    }
    setMarquee(null)
    if (!d.moved) { if (!d.additive) onSelect([]); return }
    const got = inside(data, boxFrom(d.start, at))
    if (d.additive) onSelect([...selection, ...got.filter((g) => !selection.some((r) => sameRef(r, g)))])
    else onSelect(got)
  }

  const shown = ctx.shown
  return (
    <g className={`fb-edit${space ? ' panning' : ''}${gesture !== 'select' ? ' tooling' : ''}`}>
      <rect className="fb-edit-bg" x={shown.x} y={shown.y} width={shown.w} height={shown.h} onPointerDown={(e) => begin(e, null)}
        onPointerMove={(e) => move(e)} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e)} />
      {allItems(data).map((r) => {
        const o = outlineOf(data, r)
        if (!o) return null
        const { box, rotation, centre } = o
        return (
          <rect key={refKey(r)} className={`fb-edit-hit k-${r.kind}`} data-item={refKey(r)} x={box.x} y={box.y} width={box.w} height={box.h}
            transform={rotation ? `rotate(${rotation} ${centre.x} ${centre.y})` : undefined} onPointerDown={(e) => begin(e, r)}
            onPointerMove={(e) => move(e)} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e)} />
        )
      })}
      {selection.map((r) => {
        const o = outlineOf(data, r)
        if (!o) return null
        const { box, rotation, centre } = o
        return (
          <rect key={`sel-${refKey(r)}`} className="fb-edit-sel" x={box.x - 2 * px} y={box.y - 2 * px} width={box.w + 4 * px} height={box.h + 4 * px}
            rx={4 * px} transform={rotation ? `rotate(${rotation} ${centre.x} ${centre.y})` : undefined} vectorEffect="non-scaling-stroke" />
        )
      })}
      {draft && <Draft draft={draft} gesture={gesture} px={px} cell={data.drawing?.cell ?? 32} />}
      {marquee && <rect className="fb-edit-marquee" x={marquee.x} y={marquee.y} width={marquee.w} height={marquee.h} vectorEffect="non-scaling-stroke" />}
    </g>
  )
}

/** A wall or zone being drawn, with what it measures: length and angle, or width and height, in
 *  seats (one seat is one grid cell), so it reads the same at every zoom. */
function Draft({ draft, gesture, px, cell }: { draft: { a: Point; b: Point }; gesture: string; px: number; cell: number }) {
  const { a, b } = draft
  const fmt = (n: number) => (Math.round(n * 10) / 10).toString()
  if (gesture === 'line') {
    const len = Math.hypot(b.x - a.x, b.y - a.y) / cell
    const angle = Math.round((Math.atan2(-(b.y - a.y), b.x - a.x) * 180) / Math.PI)
    return (
      <g className="fb-edit-draft">
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} vectorEffect="non-scaling-stroke" />
        <circle cx={a.x} cy={a.y} r={4 * px} />
        <text x={b.x + 10 * px} y={b.y - 10 * px} fontSize={13 * px}>{`${fmt(len)} · ${(angle + 360) % 360}°`}</text>
      </g>
    )
  }
  const box = boxFrom(a, b)
  return (
    <g className="fb-edit-draft">
      <rect x={box.x} y={box.y} width={box.w} height={box.h} vectorEffect="non-scaling-stroke" />
      <text x={box.x + box.w + 8 * px} y={box.y + box.h + 16 * px} fontSize={13 * px}>{`${fmt(box.w / cell)} × ${fmt(box.h / cell)}`}</text>
    </g>
  )
}
