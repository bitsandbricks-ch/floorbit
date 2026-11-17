import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanShape } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { fromBlock, toBlock } from './seatPlace'

/** One handle per seat of the block being arranged: drag a seat anywhere, the others stay. Seats
 *  land on half-seat steps (Alt, or snapping off, places freely); the name stays with the seat. */
export function SeatHandles({ ctx, shape, cell, snapGrid = true, onDone }: {
  ctx: OverlayContext; shape: PlanShape; cell: number; snapGrid?: boolean
  onDone: (rc: [number, number], to: [number, number]) => void
}) {
  const { t } = useTranslation()
  const drag = useRef<{ rc: [number, number]; grab: [number, number]; id: number } | null>(null)
  const [draft, setDraft] = useState<{ rc: [number, number]; at: [number, number] } | null>(null)
  const seats = shape.cells.filter((c) => c.rc).map((c) => ({
    seat: c.seat, rc: c.rc!, at: [(c.x + shape.w / 2) / cell, (c.y + shape.h / 2) / cell] as [number, number],
  }))
  const placeOf = (e: React.PointerEvent, d: NonNullable<typeof drag.current>): [number, number] => {
    const p = toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))
    const raw: [number, number] = [p[0] - d.grab[0], p[1] - d.grab[1]]
    return e.altKey || !snapGrid ? raw : [Math.round(raw[0] * 2) / 2, Math.round(raw[1] * 2) / 2]
  }
  const start = (e: React.PointerEvent, rc: [number, number], at: [number, number]) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    const p = toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))
    drag.current = { rc, grab: [p[0] - at[0], p[1] - at[1]], id: e.pointerId }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    setDraft({ rc: d.rc, at: placeOf(e, d) })
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    const to = placeOf(e, d)
    const was = seats.find((s) => s.rc[0] === d.rc[0] && s.rc[1] === d.rc[1])?.at
    setDraft(null)
    if (was && (Math.abs(was[0] - to[0]) > 0.001 || Math.abs(was[1] - to[1]) > 0.001)) onDone(d.rc, [round(to[0]), round(to[1])])
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }
  return (
    <g className="fb-edit-handles fb-edit-seats" transform={`rotate(${shape.rotation} ${shape.cx} ${shape.cy})`}>
      {seats.map((s) => {
        const at = draft && draft.rc[0] === s.rc[0] && draft.rc[1] === s.rc[1] ? draft.at : s.at
        const p = fromBlock({ ...shape, rotation: 0 }, cell, at)
        return (
          <rect key={s.seat} className={draft?.rc === s.rc ? 'fb-edit-seat moving' : 'fb-edit-seat'} data-handle="seat" data-seat={s.seat}
            x={p.x} y={p.y} width={cell} height={cell} rx={4} role="button" aria-label={t('plan.edit.seats.handle', { seat: s.seat })}
            onPointerDown={(e) => start(e, s.rc, s.at)} {...handlers} />
        )
      })}
    </g>
  )
}

const round = (v: number) => Math.round(v * 100) / 100
