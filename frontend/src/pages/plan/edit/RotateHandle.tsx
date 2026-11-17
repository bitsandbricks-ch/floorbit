import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { OverlayContext } from '../SeatMap'
import type { Box, Point } from './geometry'
import { angleTo } from './turn'

/** A handle above the one selected item that turns it to any angle round its middle, in 15° steps
 *  with Shift. ``onDraft`` shows the angle while dragging (null: back to the saved one); ``onDone``
 *  saves it. */
export function RotateHandle({ ctx, box, centre, rotation, onDraft, onDone }: {
  ctx: OverlayContext; box: Box; centre: Point; rotation: number
  onDraft: (deg: number | null) => void
  onDone: (deg: number) => void
}) {
  const { t } = useTranslation()
  const [deg, setDeg] = useState<number | null>(null)
  const drag = useRef<{ id: number; last: number | null } | null>(null)
  const px = 1 / ctx.scale
  const shown = deg ?? rotation
  // Above the top edge's middle, in the item's own (turned) frame.
  const reach = box.h / 2 + 28 * px
  const r = ((shown - 90) * Math.PI) / 180
  const at = { x: centre.x + Math.cos(r) * reach, y: centre.y + Math.sin(r) * reach }
  const edge = { x: centre.x + Math.cos(r) * (box.h / 2), y: centre.y + Math.sin(r) * (box.h / 2) }

  const start = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { id: e.pointerId, last: null }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    d.last = angleTo(centre, ctx.toPlan(e.clientX, e.clientY), e.shiftKey)
    setDeg(d.last)
    onDraft(d.last)
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    setDeg(null)
    if (d.last != null && d.last !== rotation) onDone(d.last)
    else onDraft(null)
  }

  return (
    <g className="fb-edit-rotate">
      <line x1={edge.x} y1={edge.y} x2={at.x} y2={at.y} vectorEffect="non-scaling-stroke" />
      <circle cx={at.x} cy={at.y} r={7 * px} style={{ cursor: 'grab' }} data-handle="rotate"
        onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
        <title>{t('plan.edit.rotateHandle')}</title>
      </circle>
      {deg != null && <text className="fb-edit-measure" x={at.x + 12 * px} y={at.y - 10 * px} fontSize={13 * px}>{`${deg}°`}</text>}
    </g>
  )
}
