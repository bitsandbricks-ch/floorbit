import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { OverlayContext } from '../SeatMap'
import { type Route, addBend, bendsOf, midpoints, moveBend, removeBend, snapBend } from './bends'

/** The selected cable's bends: drag one to move it, drag or click the small dot in the middle of a
 *  stretch to add one there, double-click a bend to take it out. The change is handed on when the
 *  pointer lets go; the new route stays drawn until the plan comes back with it. */
export function BendHandles({ ctx, route, cell, path, onChange }: {
  ctx: OverlayContext; route: Route; cell: number
  path: (route: Route) => string
  onChange: (route: Route) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Route | null>(null)
  const drag = useRef<{ base: Route; i: number; id: number; moved: boolean; added: boolean } | null>(null)
  const px = 1 / ctx.scale
  const shown = draft ?? route

  const start = (e: React.PointerEvent, base: Route, i: number, added: boolean) => {
    if (e.button !== 0) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { base, i, id: e.pointerId, moved: false, added }
    if (added) setDraft(base)
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    d.moved = true
    setDraft(moveBend(d.base, d.i, snapBend(ctx.toPlan(e.clientX, e.clientY), cell, e.altKey)))
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    // A click on a middle dot adds the bend right there; a click on a bend changes nothing.
    if (d.moved || d.added) onChange(draft ?? d.base)
    else setDraft(null)
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }

  return (
    <g className="fb-edit-bends">
      {draft && <path className="fb-edit-sel-line" d={path(draft)} fill="none" vectorEffect="non-scaling-stroke" />}
      {midpoints(shown).map((m, i) => (
        <circle key={`m${i}`} className="fb-edit-bend-add" cx={m.x} cy={m.y} r={4 * px} {...handlers}
          onPointerDown={(e) => start(e, addBend(shown, i, m), i, true)}>
          <title>{t('plan.edit.cable.addBend')}</title>
        </circle>
      ))}
      {bendsOf(shown).map((b, i) => (
        <circle key={`b${i}`} className="fb-edit-bend" cx={b.x} cy={b.y} r={6 * px} {...handlers}
          onPointerDown={(e) => start(e, shown, i, false)}
          onDoubleClick={(e) => { e.stopPropagation(); onChange(removeBend(shown, i)) }}>
          <title>{t('plan.edit.cable.bend')}</title>
        </circle>
      ))}
    </g>
  )
}
