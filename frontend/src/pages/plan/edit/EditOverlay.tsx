import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { SeatViewData } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { type Box, type ItemRef, type Point, allItems, boxFrom, fromPct, inside, outlineOf, refKey, sameRef, snapPct, toPct, wallCorners, wallPath } from './geometry'
import { measure, snapCorner } from './reshape'
import type { Guide } from './arrange'
import { TOOL_GESTURE, type Tool } from './tools'

/** The editor's layer over the plan: one hit area per item (switches on top, then blocks, then
 *  labels, walls and zones), the selection outlines, and a box to select by dragging on empty plan.
 *  The Hand tool, Space + drag or the middle button pans, as in drawing tools; the plan below handles that. */
export function EditOverlay({ ctx, data, selection, onSelect, onDrag, onDrop, space, tool = 'select', onPlace, onLine, onMeasure, onBox, onPointer, onMenu, onDouble, lines = [], guides = [], together = (r) => [r],
  snapping = { grid: true, items: true } }: {
  ctx: OverlayContext
  data: SeatViewData
  selection: ItemRef[]
  onSelect: (items: ItemRef[], alone?: boolean) => void
  /** While dragging: the move so far, in drawing units, and whether to snap to the grid. */
  onDrag: (d: Point, snap: boolean, lead: ItemRef, px: number) => void
  onDrop: (d: Point, snap: boolean, lead: ItemRef, px: number) => void
  /** Space is held: let the plan pan. */
  space: boolean
  tool?: Tool
  /** A placing tool was clicked here (snapped unless Alt), and exactly where (to find what is there). */
  onPlace?: (at: Point, raw: Point) => void
  /** A line was drawn (the wall tool). */
  onLine?: (a: Point, b: Point) => void
  /** The Measure tool drew a line (null: a click took it away). */
  onMeasure?: (line: { a: Point; b: Point } | null) => void
  /** A box was drawn (the zone tool). */
  onBox?: (box: Box) => void
  /** Where the pointer is over the plan (paste goes there). */
  onPointer?: (at: Point) => void
  /** Right click on an item (null: on empty plan), at a screen point. */
  onMenu?: (item: ItemRef | null, clientX: number, clientY: number) => void
  /** Double click on an item (a seat block: pick the row there), at a plan point. */
  onDouble?: (item: ItemRef, at: Point) => void
  /** Items drawn as a path (cables): hit along the line, under the other items. */
  lines?: { ref: ItemRef; d: string }[]
  /** Alignment lines to show while dragging (an edge or middle meets another item's). */
  guides?: Guide[]
  /** The items that go with one (its group): Shift-click takes them out together. */
  together?: (ref: ItemRef) => ItemRef[]
  /** Snap to the grid, and wall corners to other walls' (the top bar's toggles). */
  snapping?: { grid: boolean; items: boolean }
}) {
  const gesture = TOOL_GESTURE[tool]
  const [draft, setDraft] = useState<{ a: Point; b: Point } | null>(null)
  const lineLike = gesture === 'line' || gesture === 'measure'
  const corners = useMemo(() => (lineLike && snapping.items ? wallCorners(data) : []), [data, lineLike, snapping.items])
  // The last line the Measure tool drew stays until the next one, or another tool.
  const [measured, setMeasured] = useState<{ a: Point; b: Point; tool: Tool } | null>(null)
  const snap = (p: Point, alt: boolean, angle = false, from?: Point): Point => {
    const free = alt || !snapping.grid
    // A wall's ends land on other walls' ends and bends when near, so walls meet.
    if (lineLike) return snapCorner(p, { anchors: corners, reach: 10 / ctx.scale, from, angle, free, size: data.size })
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

  const panning = space || gesture === 'pan'
  const passes = (e: React.PointerEvent) => panning || e.button === 1
  const begin = (e: React.PointerEvent, ref: ItemRef | null) => {
    if (passes(e) || e.button === 2) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    if (gesture !== 'select') {
      const raw = ctx.toPlan(e.clientX, e.clientY)
      const at = snap(raw, e.altKey)
      if (gesture === 'click') onPlace?.(at, raw)
      else setDraft({ a: at, b: at })
      return
    }
    // Ctrl (Cmd on a Mac) picks just this item, even out of its group, so it moves on its own (Mike).
    const alone = (e.metaKey || e.ctrlKey) && !e.shiftKey
    const additive = e.shiftKey
    if (ref) {
      const picked = selection.some((r) => sameRef(r, ref))
      if (alone) onSelect([ref], true)
      else if (additive) {
        const drop = together(ref)
        onSelect(picked ? selection.filter((r) => !drop.some((x) => sameRef(x, r))) : [...selection, ref])
      }
      else if (!picked) onSelect([ref])
    }
    drag.current = { start: ctx.toPlan(e.clientX, e.clientY), lead: ref, moved: false, additive: additive || alone, id: e.pointerId }
  }
  const menu = (e: React.MouseEvent, ref: ItemRef | null) => {
    if (!onMenu) return
    e.preventDefault()
    e.stopPropagation()
    if (ref && !selection.some((r) => sameRef(r, ref))) onSelect([ref])
    onMenu(ref, e.clientX, e.clientY)
  }
  const move = (e: React.PointerEvent) => {
    onPointer?.(ctx.toPlan(e.clientX, e.clientY))
    if (draft) {
      e.stopPropagation()
      setDraft({ a: draft.a, b: snap(ctx.toPlan(e.clientX, e.clientY), e.altKey, lineLike && e.shiftKey, draft.a) })
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
      if (selection.some((r) => sameRef(r, d.lead!))) onDrag(delta, !e.altKey, d.lead, px)
    } else setMarquee(boxFrom(d.start, at))
  }
  const end = (e: React.PointerEvent) => {
    if (draft) {
      e.stopPropagation()
      setDraft(null)
      const tiny = Math.hypot(draft.b.x - draft.a.x, draft.b.y - draft.a.y) < 4 * px
      if (gesture === 'measure') { setMeasured(tiny ? null : { ...draft, tool }); onMeasure?.(tiny ? null : draft); return }
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
      if (d.moved && selection.some((r) => sameRef(r, d.lead!))) onDrop({ x: at.x - d.start.x, y: at.y - d.start.y }, !e.altKey, d.lead, px)
      else if (!d.moved && !d.additive) onSelect([d.lead])
      return
    }
    setMarquee(null)
    if (!d.moved) { if (!d.additive) onSelect([]); return }
    const got = inside(data, boxFrom(d.start, at))
    if (d.additive) onSelect([...selection, ...got.filter((g) => !selection.some((r) => sameRef(r, g)))])
    else onSelect(got)
  }

  // The hit areas don't change with zoom: steady handlers keep them from drawing again on every pan.
  const double = (e: React.MouseEvent, ref: ItemRef) => {
    if (!onDouble || gesture !== 'select' || panning) return
    e.stopPropagation()
    onDouble(ref, ctx.toPlan(e.clientX, e.clientY))
  }
  const live = useRef({ begin, menu, move, end, double })
  useEffect(() => { live.current = { begin, menu, move, end, double } })
  const on = useMemo<HitHandlers>(() => ({
    begin: (e, r) => live.current.begin(e, r), menu: (e, r) => live.current.menu(e, r),
    move: (e) => live.current.move(e), end: (e) => live.current.end(e), double: (e, r) => live.current.double(e, r),
  }), [])

  const shown = ctx.shown
  return (
    <g className={`fb-edit${panning ? ' panning' : ''}${gesture !== 'select' && gesture !== 'pan' ? ' tooling' : ''}`}>
      <rect className="fb-edit-bg" x={shown.x} y={shown.y} width={shown.w} height={shown.h} onPointerDown={(e) => begin(e, null)}
        onContextMenu={(e) => menu(e, null)}
        onPointerMove={(e) => move(e)} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e)} />
      {lines.map(({ ref, d }) => (
        <path key={refKey(ref)} className="fb-edit-hit-line" data-item={refKey(ref)} d={d} strokeWidth={10 * px} fill="none"
          onPointerDown={(e) => begin(e, ref)} onContextMenu={(e) => menu(e, ref)}
          onPointerMove={(e) => move(e)} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e)} />
      ))}
      {lines.filter((l) => selection.some((r) => sameRef(r, l.ref))).map(({ ref, d }) => (
        <path key={`sel-${refKey(ref)}`} className="fb-edit-sel-line" d={d} fill="none" vectorEffect="non-scaling-stroke" />
      ))}
      <Hits data={data} on={on} />
      {selection.map((r) => {
        const wall = r.kind === 'mark' ? data.drawing?.marks?.find((m) => m.id === r.id && m.kind === 'wall') : undefined
        if (wall) return <path key={`sel-${refKey(r)}`} className="fb-edit-sel-line" d={wallPath(wall)} fill="none" vectorEffect="non-scaling-stroke" />
        const o = outlineOf(data, r)
        if (!o) return null
        const { box, rotation, centre } = o
        return (
          <rect key={`sel-${refKey(r)}`} className="fb-edit-sel" x={box.x - 2 * px} y={box.y - 2 * px} width={box.w + 4 * px} height={box.h + 4 * px}
            rx={4 * px} transform={rotation ? `rotate(${rotation} ${centre.x} ${centre.y})` : undefined} vectorEffect="non-scaling-stroke" />
        )
      })}
      {guides.map((g, i) => (g.axis === 'x'
        ? <line key={i} className="fb-edit-guide" x1={g.at} x2={g.at} y1={shown.y} y2={shown.y + shown.h} vectorEffect="non-scaling-stroke" />
        : <line key={i} className="fb-edit-guide" y1={g.at} y2={g.at} x1={shown.x} x2={shown.x + shown.w} vectorEffect="non-scaling-stroke" />))}
      {draft && <Draft draft={draft} gesture={lineLike ? 'line' : gesture} px={px} cell={data.drawing?.cell ?? 32} seatM={data.seat_m} />}
      {!draft && measured && measured.tool === tool && <Draft draft={measured} gesture="line" px={px} cell={data.drawing?.cell ?? 32} seatM={data.seat_m} />}
      {marquee && <rect className="fb-edit-marquee" x={marquee.x} y={marquee.y} width={marquee.w} height={marquee.h} vectorEffect="non-scaling-stroke" />}
    </g>
  )
}

/** A wall or zone being drawn, with what it measures: length and angle, or width and height, in
 *  seats (one seat is one grid cell), so it reads the same at every zoom. */
function Draft({ draft, gesture, px, cell, seatM }: { draft: { a: Point; b: Point }; gesture: string; px: number; cell: number; seatM?: number | null }) {
  const { a, b } = draft
  const fmt = (n: number) => (Math.round(n * 10) / 10).toString()
  if (gesture === 'line') {
    return (
      <g className="fb-edit-draft">
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} vectorEffect="non-scaling-stroke" />
        <circle cx={a.x} cy={a.y} r={4 * px} />
        <text x={b.x + 10 * px} y={b.y - 10 * px} fontSize={13 * px}>{measure(a, b, cell, seatM)}</text>
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

interface HitHandlers {
  begin: (e: React.PointerEvent, ref: ItemRef) => void
  menu: (e: React.MouseEvent, ref: ItemRef) => void
  move: (e: React.PointerEvent) => void
  end: (e: React.PointerEvent) => void
  double: (e: React.MouseEvent, ref: ItemRef) => void
}

/** One hit area per item (switches on top, then blocks, then labels, walls and zones). */
const Hits = memo(function Hits({ data, on }: { data: SeatViewData; on: HitHandlers }) {
  return (
    <>
      {allItems(data).map((r) => {
        const wall = r.kind === 'mark' ? data.drawing?.marks?.find((m) => m.id === r.id && m.kind === 'wall') : undefined
        if (wall) {
          // Along the wall, not its box: an L-shaped wall would cover what sits in its corner.
          return (
            <path key={refKey(r)} className="fb-edit-hit fb-edit-hit-wall k-mark" data-item={refKey(r)} d={wallPath(wall)} strokeWidth={16}
              onPointerDown={(e) => on.begin(e, r)} onContextMenu={(e) => on.menu(e, r)}
              onPointerMove={on.move} onPointerUp={on.end} onPointerCancel={on.end} />
          )
        }
        const o = outlineOf(data, r)
        if (!o) return null
        const { box, rotation, centre } = o
        return (
          <rect key={refKey(r)} className={`fb-edit-hit k-${r.kind}`} data-item={refKey(r)} x={box.x} y={box.y} width={box.w} height={box.h}
            transform={rotation ? `rotate(${rotation} ${centre.x} ${centre.y})` : undefined} onPointerDown={(e) => on.begin(e, r)}
            onContextMenu={(e) => on.menu(e, r)} onDoubleClick={(e) => on.double(e, r)}
            onPointerMove={on.move} onPointerUp={on.end} onPointerCancel={on.end} />
        )
      })}
    </>
  )
})
