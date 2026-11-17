import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanMark } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { addBend, midpoints, removeBend } from './bends'
import { type Point, wallRoute } from './geometry'
import { measure, snapCorner, withRoute } from './reshape'

/** The selected wall's corners: drag an end or a bend to move it, drag or click the dot in the
 *  middle of a stretch to add a bend there, double-click a bend to take it out. Each stretch shows
 *  its length (in seats) and angle. Corners snap onto other walls' ends and bends so walls meet,
 *  keep 15° steps with Shift, and leave the grid with Alt. */
export function WallHandles({ ctx, mark, size, cell, anchors, snapGrid = true, seatM, onDraft, onDone }: {
  ctx: OverlayContext; mark: PlanMark; size: { w: number; h: number }; cell: number
  /** Other walls' ends and bends, in drawing units. */
  anchors: Point[]
  /** Off: corners land where they are dropped, as with Alt. */
  snapGrid?: boolean
  /** Metres per seat, to show lengths in metres too. */
  seatM?: number | null
  onDraft: (m: PlanMark | null) => void
  onDone: (m: PlanMark) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Point[] | null>(null)
  const drag = useRef<{ base: Point[]; i: number; id: number; moved: boolean; added: boolean } | null>(null)
  const px = 1 / ctx.scale
  const route = draft ?? wallRoute(mark)
  const last = route.length - 1

  const show = (r: Point[] | null) => { setDraft(r); onDraft(r ? withRoute(mark, r) : null) }
  const start = (e: React.PointerEvent, base: Point[], i: number, added: boolean) => {
    if (e.button !== 0) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { base, i, id: e.pointerId, moved: false, added }
    if (added) show(base)
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    d.moved = true
    const from = d.base[d.i === 0 ? 1 : d.i - 1]
    const at = snapCorner(ctx.toPlan(e.clientX, e.clientY), { anchors, reach: 10 * px, from, angle: e.shiftKey, free: e.altKey || !snapGrid, size })
    show(d.base.map((p, k) => (k === d.i ? at : p)))
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    const r = draft ?? d.base
    const a = r[0], b = r[r.length - 1]
    // A straight wall needs two different ends; a click on a corner changes nothing.
    if ((d.moved || d.added) && (r.length > 2 || a.x !== b.x || a.y !== b.y)) onDone(withRoute(mark, r))
    else show(null)
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }
  // Corner i among the bends is route point i + 1: bends.ts counts that way.
  const bendIndex = (i: number) => i - 1

  return (
    <g className="fb-edit-handles fb-edit-wall">
      {route.slice(1).map((b, i) => {
        const a = route[i]
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
        return (
          <text key={`m${i}`} className="fb-edit-measure" x={mid.x + 8 * px} y={mid.y - 8 * px} fontSize={12 * px}>{measure(a, b, cell, seatM)}</text>
        )
      })}
      {midpoints(route).map((m, i) => (
        <circle key={`a${i}`} className="fb-edit-bend-add" cx={m.x} cy={m.y} r={4 * px} {...handlers}
          onPointerDown={(e) => start(e, addBend(route, i, m), i + 1, true)}>
          <title>{t('plan.edit.wall.addBend')}</title>
        </circle>
      ))}
      {route.map((p, i) => (i === 0 || i === last
        ? (
          <rect key={`e${i}`} className="fb-edit-handle" data-handle={i === 0 ? 'a' : 'b'} x={p.x - 5 * px} y={p.y - 5 * px} width={10 * px} height={10 * px}
            rx={2 * px} style={{ cursor: 'move' }} {...handlers} onPointerDown={(e) => start(e, route, i, false)}>
            <title>{t('plan.edit.mark.handleEnd')}</title>
          </rect>
        ) : (
          <circle key={`b${i}`} className="fb-edit-bend" data-handle={`bend-${i}`} cx={p.x} cy={p.y} r={6 * px} {...handlers}
            onPointerDown={(e) => start(e, route, i, false)}
            onDoubleClick={(e) => { e.stopPropagation(); onDone(withRoute(mark, removeBend(route, bendIndex(i)))) }}>
            <title>{t('plan.edit.wall.bend')}</title>
          </circle>
        )))}
    </g>
  )
}

