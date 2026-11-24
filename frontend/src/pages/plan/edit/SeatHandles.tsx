import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanShape } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { type Guide, type Pt, alignSeats } from './seatGuides'
import { fromBlock, toBlock } from './seatPlace'
import './SeatHandles.css'

type RC = [number, number]
export type SeatMove = { rc: RC; to: Pt }
const same = (a: RC, b: RC) => a[0] === b[0] && a[1] === b[1]
const rcKey = (rc: RC) => `${rc[0]},${rc[1]}`

/** One handle per seat of the block being arranged: drag a seat anywhere, the others stay. Shift-
 *  or Ctrl-click picks more seats, which then move together (Mike: multi-select when placing seats
 *  freely); guides show when a seat lines up with another, and two picked seats can swap places.
 *  Seats land on half-seat steps (Alt, or snapping off, places freely); the name stays with the seat. */
export function SeatHandles({ ctx, shape, cell, snapGrid = true, onDone }: {
  ctx: OverlayContext; shape: PlanShape; cell: number; snapGrid?: boolean
  onDone: (moves: SeatMove[]) => void
}) {
  const { t } = useTranslation()
  const drag = useRef<{ rc: RC; grab: Pt; id: number; moving: RC[] } | null>(null)
  const [picked, setPicked] = useState<RC[]>([])
  const [draft, setDraft] = useState<{ moving: RC[]; by: Pt; guides: Guide[] } | null>(null)
  const seats = shape.cells.filter((c) => c.rc).map((c) => ({
    seat: c.seat, rc: c.rc!, at: [(c.x + shape.w / 2) / cell, (c.y + shape.h / 2) / cell] as Pt,
  }))
  const atOf = (rc: RC) => seats.find((s) => same(s.rc, rc))?.at
  // Picks of seats no longer in the block (rows changed) drop out.
  const pickedNow = picked.filter((rc) => atOf(rc))
  const isPicked = (rc: RC) => pickedNow.some((p) => same(p, rc))

  const shiftOf = (e: React.PointerEvent, d: NonNullable<typeof drag.current>) => {
    const p = toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))
    const from = atOf(d.rc) ?? [0, 0]
    const raw: Pt = [p[0] - d.grab[0], p[1] - d.grab[1]]
    if (e.altKey || !snapGrid) return { by: [raw[0] - from[0], raw[1] - from[1]] as Pt, guides: [] }
    const snapped: Pt = [Math.round(raw[0] * 2) / 2 - from[0], Math.round(raw[1] * 2) / 2 - from[1]]
    const moving = d.moving.map((rc) => atOf(rc)!).filter(Boolean)
    const others = seats.filter((s) => !d.moving.some((m) => same(m, s.rc))).map((s) => s.at)
    return alignSeats(moving, others, snapped)
  }
  const start = (e: React.PointerEvent, rc: RC, at: Pt) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      // Adds or takes out a seat; no drag, so a stray move doesn't shift the selection.
      setPicked(isPicked(rc) ? pickedNow.filter((p) => !same(p, rc)) : [...pickedNow, rc])
      return
    }
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    const p = toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))
    // A picked seat takes the other picked ones along; any other seat moves alone and is picked.
    const moving = isPicked(rc) ? pickedNow : [rc]
    if (!isPicked(rc)) setPicked([rc])
    drag.current = { rc, grab: [p[0] - at[0], p[1] - at[1]], id: e.pointerId, moving }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    setDraft({ moving: d.moving, ...shiftOf(e, d) })
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    const { by } = shiftOf(e, d)
    setDraft(null)
    if (Math.abs(by[0]) < 0.001 && Math.abs(by[1]) < 0.001) return
    onDone(d.moving.map((rc) => { const at = atOf(rc)!; return { rc, to: [round(at[0] + by[0]), round(at[1] + by[1])] as Pt } }))
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }
  const flat = { ...shape, rotation: 0 }
  const plot = (p: Pt) => fromBlock(flat, cell, p)

  // Two picked seats: a button between them swaps their places (their names and ports stay with them).
  const pair = !draft && pickedNow.length === 2 ? pickedNow.map((rc) => seats.find((s) => same(s.rc, rc))!) : null
  const swap = pair ? plot([(pair[0].at[0] + pair[1].at[0]) / 2 + 0.5, (pair[0].at[1] + pair[1].at[1]) / 2 + 0.5]) : null
  const k = 1 / ctx.scale
  return (
    <g className="fb-edit-handles fb-edit-seats" transform={`rotate(${shape.rotation} ${shape.cx} ${shape.cy})`}>
      {seats.map((s) => {
        const moving = draft?.moving.some((m) => same(m, s.rc))
        const p = plot(moving ? [s.at[0] + draft!.by[0], s.at[1] + draft!.by[1]] : s.at)
        const cls = ['fb-edit-seat', moving && 'moving', isPicked(s.rc) && 'picked'].filter(Boolean).join(' ')
        return (
          <rect key={rcKey(s.rc)} className={cls} data-handle="seat" data-seat={s.seat} aria-pressed={isPicked(s.rc)}
            x={p.x} y={p.y} width={cell} height={cell} rx={4} role="button" aria-label={t('freeSeats.handle', { seat: s.seat })}
            onPointerDown={(e) => start(e, s.rc, s.at)} {...handlers} />
        )
      })}
      {draft?.guides.map((g, i) => {
        const a = 'x' in g ? plot([g.x, g.from - 2]) : plot([g.from - 2, g.y])
        const b = 'x' in g ? plot([g.x, g.to + 2]) : plot([g.to + 2, g.y])
        return <line key={i} className="fb-seat-guide" data-guide={'x' in g ? 'column' : 'row'} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
      })}
      {pair && swap && (
        <g className="fb-seat-swap" role="button" aria-label={t('freeSeats.swap', { a: pair[0].seat, b: pair[1].seat })}
          transform={`translate(${swap.x} ${swap.y}) rotate(${-shape.rotation}) scale(${k})`}
          onPointerDown={(e) => {
            if (e.button !== 0) return
            e.stopPropagation()
            e.preventDefault()
            onDone([{ rc: pair[0].rc, to: pair[1].at }, { rc: pair[1].rc, to: pair[0].at }])
          }}>
          <rect x={-34} y={-12} width={68} height={24} rx={12} />
          <text dy="0.35em" textAnchor="middle">{t('freeSeats.swapShort')}</text>
        </g>
      )}
    </g>
  )
}

const round = (v: number) => Math.round(v * 100) / 100
