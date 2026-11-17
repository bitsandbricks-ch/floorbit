import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { OverlayContext } from '../SeatMap'
import type { Box } from './geometry'

/** The background's frame while it is being placed: drag inside to move it, the corner to scale it
 *  (it keeps its shape). ``onDone`` gets the new frame in drawing units. */
export function BackgroundHandles({ ctx, frame, onDraft, onDone }: {
  ctx: OverlayContext; frame: Box
  onDraft: (f: Box | null) => void
  onDone: (f: Box) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Box | null>(null)
  const drag = useRef<{ id: number; how: 'move' | 'scale'; x: number; y: number; last: Box | null } | null>(null)
  const px = 1 / ctx.scale
  const f = draft ?? frame
  const start = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    // No text gets selected on the page while dragging.
    e.preventDefault()
    const how = (e.currentTarget as Element).getAttribute('data-handle') === 'background-scale' ? 'scale' : 'move'
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    const p = ctx.toPlan(e.clientX, e.clientY)
    drag.current = { id: e.pointerId, how, x: p.x, y: p.y, last: null }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    const p = ctx.toPlan(e.clientX, e.clientY)
    let next: Box
    if (d.how === 'move') next = { ...frame, x: frame.x + p.x - d.x, y: frame.y + p.y - d.y }
    else {
      // Scaled from the top left corner, by how far the pointer went along the diagonal.
      const k = Math.max(0.05, Math.max((p.x - frame.x) / frame.w, (p.y - frame.y) / frame.h))
      next = { ...frame, w: frame.w * k, h: frame.h * k }
    }
    d.last = next
    setDraft(next)
    onDraft(next)
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    setDraft(null)
    if (d.last) onDone(d.last)
    else onDraft(null)
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }
  return (
    <g className="fb-edit-bgframe">
      <rect x={f.x} y={f.y} width={f.w} height={f.h} vectorEffect="non-scaling-stroke" style={{ cursor: 'move' }} data-handle="background"
        onPointerDown={start} {...handlers}>
        <title>{t('plan.edit.background.dragHelp')}</title>
      </rect>
      <rect className="corner" x={f.x + f.w - 6 * px} y={f.y + f.h - 6 * px} width={12 * px} height={12 * px} style={{ cursor: 'nwse-resize' }}
        data-handle="background-scale" onPointerDown={start} {...handlers} />
    </g>
  )
}
