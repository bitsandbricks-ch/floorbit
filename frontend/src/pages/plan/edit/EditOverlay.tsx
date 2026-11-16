import { useRef, useState } from 'react'
import type { SeatViewData } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { type Box, type ItemRef, type Point, allItems, boxFrom, inside, outlineOf, refKey, sameRef } from './geometry'

/** The editor's layer over the plan: one hit area per item (switches on top, then blocks, then
 *  labels, walls and zones), the selection outlines, and a box to select by dragging on empty plan.
 *  Space + drag or the middle button pans, as in drawing tools; the plan below handles that. */
export function EditOverlay({ ctx, data, selection, onSelect, onDrag, onDrop, space }: {
  ctx: OverlayContext
  data: SeatViewData
  selection: ItemRef[]
  onSelect: (items: ItemRef[]) => void
  /** While dragging: the move so far, in drawing units, and whether to snap to the grid. */
  onDrag: (d: Point, snap: boolean, lead: ItemRef) => void
  onDrop: (d: Point, snap: boolean, lead: ItemRef) => void
  /** Space is held: let the plan pan. */
  space: boolean
}) {
  const drag = useRef<{ start: Point; lead: ItemRef | null; moved: boolean; additive: boolean; id: number } | null>(null)
  const [marquee, setMarquee] = useState<Box | null>(null)
  const px = 1 / ctx.scale   // one screen pixel in drawing units

  const passes = (e: React.PointerEvent) => space || e.button === 1
  const begin = (e: React.PointerEvent, ref: ItemRef | null) => {
    if (passes(e) || e.button === 2) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    const additive = e.shiftKey || e.metaKey || e.ctrlKey
    if (ref) {
      const picked = selection.some((r) => sameRef(r, ref))
      if (additive) onSelect(picked ? selection.filter((r) => !sameRef(r, ref)) : [...selection, ref])
      else if (!picked) onSelect([ref])
    }
    drag.current = { start: ctx.toPlan(e.clientX, e.clientY), lead: ref, moved: false, additive, id: e.pointerId }
  }
  const move = (e: React.PointerEvent) => {
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
    <g className={`fb-edit${space ? ' panning' : ''}`}>
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
      {marquee && <rect className="fb-edit-marquee" x={marquee.x} y={marquee.y} width={marquee.w} height={marquee.h} vectorEffect="non-scaling-stroke" />}
    </g>
  )
}
