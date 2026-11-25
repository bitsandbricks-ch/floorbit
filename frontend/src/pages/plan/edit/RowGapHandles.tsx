import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanShape } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { colGapBoxes, draggedGap, gapSpots, rowBoxes } from './rowGaps'
import { toBlock } from './seatPlace'
import './RowGapHandles.css'

/** A bar between each two rows of the selected block: drag it up or down to change the space above
 *  the lower row (quarter seats; Alt, or snapping off, places freely). Clicking a bar picks that row.
 *  The picked row is outlined. */
export function RowGapHandles({ ctx, shape, cell, gaps, picked, snapGrid = true, onPick, onDone }: {
  ctx: OverlayContext; shape: PlanShape; cell: number
  /** Each row's space above it now, in seats, top row first. */
  gaps: number[]
  /** The picked row's place in the block. */
  picked: number | null
  snapGrid?: boolean
  onPick: (row: number) => void
  onDone: (row: number, gap: number) => void
}) {
  const { t } = useTranslation()
  const drag = useRef<{ row: number; from: number; id: number; moved: boolean } | null>(null)
  const [draft, setDraft] = useState<{ row: number; gap: number } | null>(null)
  const spots = gapSpots(shape, cell)
  const boxes = rowBoxes(shape, cell)
  const colGaps = colGapBoxes(shape, cell)
  const px = 1 / ctx.scale / cell   // one screen pixel, in seats
  const at = (e: React.PointerEvent) => toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))[1]
  const start = (e: React.PointerEvent, row: number) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { row, from: at(e), id: e.pointerId, moved: false }
  }
  const gapOf = (e: React.PointerEvent, d: NonNullable<typeof drag.current>) => draggedGap(gaps[d.row] ?? 0, at(e) - d.from, e.altKey || !snapGrid)
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    if (!d.moved && Math.abs(at(e) - d.from) < 3 * px) return
    d.moved = true
    setDraft({ row: d.row, gap: gapOf(e, d) })
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    setDraft(null)
    if (!d.moved) { onPick(d.row); return }
    const gap = gapOf(e, d)
    if (gap !== (gaps[d.row] ?? 0)) onDone(d.row, gap)
  }
  const ox = shape.cx - shape.w / 2, oy = shape.cy - shape.h / 2
  const box = picked != null ? boxes[picked] : null
  const bar = Math.max(0.3, 8 * px)
  const fmt = (n: number) => String(Math.round(n * 100) / 100)
  return (
    <g className="fb-edit-handles fb-row-gaps" transform={`rotate(${shape.rotation} ${shape.cx} ${shape.cy})`}>
      {/* Spacers and gaps show hatched while editing, so they read as things to grab (#1547). */}
      <defs>
        <pattern id="fb-spacer-hatch" patternUnits="userSpaceOnUse" width={cell * 0.3} height={cell * 0.3} patternTransform="rotate(45)">
          <line className="fb-spacer-hatch-line" x1={0} y1={0} x2={0} y2={cell * 0.3} />
        </pattern>
      </defs>
      {colGaps.map((g, i) => (
        <rect key={`c${i}`} className="fb-row-col-gap" x={ox + g.x * cell} y={oy + g.y * cell} width={g.w * cell} height={cell} rx={3} />
      ))}
      {box && <rect className="fb-row-picked" x={ox + (box.left - 0.15) * cell} y={oy + (box.top - 0.15) * cell}
        width={(box.right - box.left + 0.3) * cell} height={(box.bottom - box.top + 0.3) * cell} rx={4} data-picked-row={picked} />}
      {spots.map((s) => {
        // While dragged, the bar follows the pointer by the change, so it stays under it.
        const moved = draft?.row === s.row ? (draft.gap - (gaps[s.row] ?? 0)) : 0
        const y = oy + (s.y + moved) * cell
        const x = ox + s.x1 * cell, w = (s.x2 - s.x1) * cell
        // A spacer fills the room between the rows; with none the bar is a thin handle.
        const h = Math.max(bar, s.h + moved) * cell
        return (
          <g key={s.row}>
            <rect className={`fb-row-gap-bar${draft?.row === s.row ? ' moving' : ''}${s.h + moved > bar ? ' spacer' : ''}`} data-handle="row-gap" data-row={s.row}
              x={x} y={y - h / 2} width={w} height={h} rx={3} role="button"
              aria-label={t('blockRows.gapHandle', { name: shape.row_list?.[s.row]?.name ?? String(s.row + 1) })}
              onPointerDown={(e) => start(e, s.row)} onPointerMove={move} onPointerUp={end} onPointerCancel={end} />
            <line className="fb-row-gap-grip" x1={x + w / 2 - 0.4 * cell} x2={x + w / 2 + 0.4 * cell} y1={y} y2={y} />
            {draft?.row === s.row && (
              <text className="fb-row-gap-label" x={x + w + 0.3 * cell} y={y} dominantBaseline="middle" fontSize={14 / ctx.scale}>
                {t('blockRows.gapDraft', { count: draft.gap, value: fmt(draft.gap) })}
              </text>
            )}
          </g>
        )
      })}
    </g>
  )
}
