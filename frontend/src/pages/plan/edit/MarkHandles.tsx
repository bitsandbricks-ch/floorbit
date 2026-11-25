import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanMark } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import type { Point } from './geometry'
import { type Handle, handlesOf, reshape } from './reshape'
import { WallHandles } from './WallHandles'
import { isLine } from '../lineMarks'

const CURSOR: Record<Handle, string> = { scale: 'nwse-resize', nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', a: 'move', b: 'move' }

/** Handles on the one selected mark: drag a label's or icon's corner to make it bigger or smaller,
 *  a zone's corners to resize it; a wall gets WallHandles (ends, bends, lengths). Snaps to the grid (or to tenths of
 *  the size) unless Alt is held. ``onDraft`` shows the mark while dragging; ``onDone`` saves it. */
export function MarkHandles({ ctx, mark, corner, size, cell = 32, anchors = [], snapGrid = true, seatM, onDraft, onDone }: {
  ctx: OverlayContext; mark: PlanMark; corner: Point; size: { w: number; h: number }
  /** A wall's: the grid cell (for its lengths) and the other walls' corners it snaps to. */
  cell?: number; anchors?: Point[]
  /** Off: handles land where they are dropped, as with Alt. */
  snapGrid?: boolean
  seatM?: number | null
  onDraft: (m: PlanMark | null) => void
  onDone: (m: PlanMark) => void
}) {
  if (isLine(mark)) return <WallHandles ctx={ctx} mark={mark} size={size} cell={cell} anchors={anchors} snapGrid={snapGrid} seatM={seatM} onDraft={onDraft} onDone={onDone} />
  return <BoxHandles ctx={ctx} mark={mark} corner={corner} size={size} snapGrid={snapGrid} onDraft={onDraft} onDone={onDone} />
}

function BoxHandles({ ctx, mark, corner, size, snapGrid, onDraft, onDone }: {
  ctx: OverlayContext; mark: PlanMark; corner: Point; size: { w: number; h: number }; snapGrid: boolean
  onDraft: (m: PlanMark | null) => void
  onDone: (m: PlanMark) => void
}) {
  const { t } = useTranslation()
  const drag = useRef<{ handle: Handle; base: PlanMark; from: Point; id: number; last: PlanMark | null } | null>(null)
  const px = 1 / ctx.scale

  const start = (e: React.PointerEvent, handle: Handle, at: Point) => {
    if (e.button !== 0) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { handle, base: mark, from: at, id: e.pointerId, last: null }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    d.last = reshape(d.base, d.handle, ctx.toPlan(e.clientX, e.clientY), d.from, size, e.altKey || !snapGrid)
    onDraft(d.last)
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    if (d.last && d.last !== d.base) onDone(d.last)
    else onDraft(null)
  }

  return (
    <g className="fb-edit-handles">
      {handlesOf(mark, corner).map(([h, p]) => (
        <rect key={h} className="fb-edit-handle" data-handle={h} x={p.x - 5 * px} y={p.y - 5 * px} width={10 * px} height={10 * px} rx={2 * px}
          style={{ cursor: CURSOR[h] }} onPointerDown={(e) => start(e, h, p)} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
          <title>{t(h === 'a' || h === 'b' ? 'plan.edit.mark.handleEnd' : 'plan.edit.mark.handleSize')}</title>
        </rect>
      ))}
      {!isLine(mark) && mark.kind !== 'zone' && (mark.scale ?? 1) !== 1 && (
        <text className="fb-edit-handle-label" x={handlesOf(mark, corner)[0][1].x + 8 * px} y={handlesOf(mark, corner)[0][1].y + 16 * px}
          fontSize={12 * px}>{`${Math.round((mark.scale ?? 1) * 100)} %`}</text>
      )}
    </g>
  )
}
