import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanShape } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { type BlockRow, withLabel } from './rows'
import { type Pt, drawnSeats, rowOffset } from './rowShapes'
import { toBlock } from './seatPlace'
import './RowGapHandles.css'

/** The picked row's letter on the plan, to drag anywhere (Mike: "let me move the row label around").
 *  It is kept in the row's own frame, so it moves with the row when the row or the block moves. */
export function RowLabelHandle({ ctx, shape, cell, row, r, snapGrid = true, onDone }: {
  ctx: OverlayContext; shape: PlanShape; cell: number; row: BlockRow; r: number
  snapGrid?: boolean
  onDone: (row: BlockRow) => void
}) {
  const { t } = useTranslation()
  const drag = useRef<{ id: number; moved: boolean } | null>(null)
  const [draft, setDraft] = useState<Pt | null>(null)
  const labels = (shape.rows ?? []).filter((l) => l.r === r)
  const drawn = drawnSeats(shape, cell, r)
  if (!labels.length || !drawn.length) return null
  const off = rowOffset(row, drawn)
  const ox = shape.cx - shape.w / 2, oy = shape.cy - shape.h / 2
  const at = (p: Pt) => ({ x: ox + p[0] * cell, y: oy + p[1] * cell })
  // Half a seat at a time, unless snapping is off or Alt is held.
  const point = (e: React.PointerEvent): Pt => {
    const p = toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))
    const snap = (v: number) => (e.altKey || !snapGrid ? Math.round(v * 100) / 100 : Math.round(v * 2) / 2)
    return [snap(p[0]), snap(p[1])]
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    setDraft(null)
    if (!d.moved) return
    const p = point(e)
    const keep = (v: number) => Math.round(v * 100) / 100 + 0
    onDone(withLabel(row, 'moved', [keep(p[0] - off[0]), keep(p[1] - off[1])]))
  }
  const name = shape.row_list?.[r]?.name ?? labels[0].text
  const r6 = 6 / ctx.scale
  return (
    <g className="fb-edit-handles fb-row-labels" transform={`rotate(${shape.rotation} ${shape.cx} ${shape.cy})`}>
      {labels.map((l, i) => {
        const p = draft && i === 0 ? at(draft) : at([(l.x + shape.w / 2) / cell, (l.y + shape.h / 2) / cell])
        if (draft && i > 0) return null
        return (
          <circle key={i} className="fb-row-label-handle" data-handle="row-label" cx={p.x} cy={p.y} r={Math.max(r6 * 1.6, cell * 0.45)}
            role="button" aria-label={t('blockRows.labelHandle', { name })}
            onPointerDown={(e) => {
              if (e.button !== 0) return
              e.stopPropagation()
              e.preventDefault()
              ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
              drag.current = { id: e.pointerId, moved: false }
            }}
            onPointerMove={(e) => {
              const d = drag.current
              if (!d || d.id !== e.pointerId) return
              e.stopPropagation()
              d.moved = true
              setDraft(point(e))
            }}
            onPointerUp={end} onPointerCancel={end} />
        )
      })}
      {draft && (() => { const p = at(draft); return <text className="fb-row-gap-label" x={p.x} y={p.y} dy="0.35em" textAnchor="middle" fontSize={cell * 0.6}>{labels[0].text}</text> })()}
    </g>
  )
}
