import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanShape } from '@/api/types'
import type { OverlayContext } from '../SeatMap'
import { piecesOf, withPiecePath } from './pieces'
import type { BlockRow } from './rows'
import { type Pt, addPoint, armEnds, bendThrough, drawnSeats, dropPoint, movePoint, reshaped, rowOffset, turnOver, turnedOnce, withArm } from './rowShapes'
import { toBlock } from './seatPlace'
import './RowGapHandles.css'

type Grab = { kind: 'bend' } | { kind: 'arm'; arm: number; from: Pt; grow: Pt } | { kind: 'point'; i: number; k: number }

/** Handles to shape the picked row of the selected block on the plan: an arc's middle (drag to bend
 *  it), a U's or L's arm ends (drag to make an arm longer, the others give the seats), and a path's
 *  points (drag to move, + halfway along a leg adds one, double-click or Alt-click takes one out). */
export function RowShapeHandles({ ctx, shape, cell, size, rows, r, snapGrid = true, onDone }: {
  ctx: OverlayContext; shape: PlanShape; cell: number; size: { w: number; h: number }
  /** The block's rows as the server keeps them, and the place of the one to shape. */
  rows: BlockRow[]; r: number
  snapGrid?: boolean
  /** The new row, and the block's x/y (%) that keeps the row's anchor seat in place. */
  onDone: (row: BlockRow, place: { x: number; y: number }) => void
}) {
  const row = rows[r]
  const { t } = useTranslation()
  const drag = useRef<{ grab: Grab; id: number; moved: boolean } | null>(null)
  const [draft, setDraft] = useState<{ row: BlockRow; first: boolean } | null>(null)
  const drawn = drawnSeats(shape, cell, r)
  const off = rowOffset(row, drawn)
  if (!drawn.length) return null
  const ox = shape.cx - shape.w / 2, oy = shape.cy - shape.h / 2
  const at = (p: Pt) => ({ x: ox + p[0] * cell, y: oy + p[1] * cell })
  const toRow = (p: Pt): Pt => [p[0] - off[0], p[1] - off[1]]
  const fromRow = (p: Pt): Pt => [p[0] + off[0], p[1] + off[1]]
  const pointer = (e: React.PointerEvent | React.MouseEvent): Pt => toBlock(shape, cell, ctx.toPlan(e.clientX, e.clientY))

  const done = (next: BlockRow, first = false) => {
    if (JSON.stringify(next) === JSON.stringify(row)) return
    const { x, y } = reshaped(shape, cell, size, rows, r, next, first)
    onDone(next, { x, y })
  }
  // The row's anchor is its first seat, on the first point of the first piece.
  const firstMoves = (g: Grab) => g.kind === 'point' && g.k === 0 && g.i === 0
  const pathOf = (k: number): Pt[] => piecesOf(row)[k]?.path ?? []
  const shaped = (g: Grab, e: React.PointerEvent): BlockRow => {
    const p = pointer(e), free = e.altKey || !snapGrid
    // Turned over once, the row bows the other way from how its seats now read.
    if (g.kind === 'bend') return { ...row, bend: (turnedOnce(row) ? -1 : 1) * bendThrough(drawn[0], drawn[drawn.length - 1], p, free) || 0 }
    if (g.kind === 'arm') return withArm(row, g.arm, (p[0] - g.from[0]) * g.grow[0] + (p[1] - g.from[1]) * g.grow[1])
    return withPiecePath(row, g.k, movePoint(pathOf(g.k), g.i, turnOver(row, toRow(p)), free))
  }
  const start = (e: React.PointerEvent, grab: Grab) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    if (grab.kind === 'point' && e.altKey) { done(withPiecePath(row, grab.k, dropPoint(pathOf(grab.k), grab.i)), firstMoves(grab)); return }
    ;(e.currentTarget as Element).setPointerCapture?.(e.pointerId)
    drag.current = { grab, id: e.pointerId, moved: false }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    d.moved = true
    setDraft({ row: shaped(d.grab, e), first: firstMoves(d.grab) })
  }
  const end = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    e.stopPropagation()
    drag.current = null
    setDraft(null)
    if (!d.moved) return
    done(shaped(d.grab, e), firstMoves(d.grab))
  }
  const handlers = { onPointerMove: move, onPointerUp: end, onPointerCancel: end }
  const r6 = 6 / ctx.scale
  const name = shape.row_list?.[r]?.name ?? String(r + 1)

  // While dragging, the seats where they will land, the anchor seat staying put.
  const preview = draft ? reshaped(shape, cell, size, rows, r, draft.row, draft.first).seats : null
  const handles: React.ReactNode[] = []
  if (row.shape === 'arc') {
    const n = drawn.length
    const mid: Pt = n % 2 ? drawn[(n - 1) / 2] : [(drawn[n / 2 - 1][0] + drawn[n / 2][0]) / 2, (drawn[n / 2 - 1][1] + drawn[n / 2][1]) / 2]
    const p = at(preview ? (n % 2 ? preview[(n - 1) / 2] : [(preview[n / 2 - 1][0] + preview[n / 2][0]) / 2, (preview[n / 2 - 1][1] + preview[n / 2][1]) / 2]) : mid)
    handles.push(
      <circle key="bend" className="fb-row-shape-handle" data-handle="bend" cx={p.x} cy={p.y} r={r6 * 1.3} role="button"
        aria-label={t('blockRows.bendHandle', { name })} onPointerDown={(e) => start(e, { kind: 'bend' })} {...handlers} />,
    )
    if (draft) handles.push(<text key="bend-label" className="fb-row-gap-label" x={p.x + 12 / ctx.scale} y={p.y - 12 / ctx.scale} fontSize={14 / ctx.scale}>{`${draft.row.bend ?? 0}°`}</text>)
  }
  if (row.shape === 'u' || row.shape === 'l') {
    for (const end of armEnds(row)) {
      // Just past the arm's outer seat, so the seat's number stays readable.
      const p = at(fromRow([end.at[0] + end.grow[0] * 0.85, end.at[1] + end.grow[1] * 0.85]))
      handles.push(
        <rect key={`arm-${end.arm}`} className="fb-row-shape-handle" data-handle="arm" data-arm={end.arm} x={p.x - r6} y={p.y - r6} width={2 * r6} height={2 * r6} rx={2 / ctx.scale}
          role="button" aria-label={t('blockRows.armHandle', { name, arm: end.arm + 1 })}
          onPointerDown={(e) => start(e, { kind: 'arm', arm: end.arm, from: pointer(e), grow: end.grow })} {...handlers} />,
      )
    }
    if (draft?.row.sides) handles.push(<text key="arm-label" className="fb-row-gap-label" x={at(drawn[0]).x} y={at(drawn[0]).y - 22 / ctx.scale} fontSize={14 / ctx.scale}>{draft.row.sides.join(' · ')}</text>)
  }
  if (row.shape === 'path' && row.path?.length) {
    // While dragging, the paths where the new layout puts them; each piece in its own colour.
    const o = draft && preview ? rowOffset(draft.row, preview) : off
    piecesOf(draft?.row ?? row).forEach((piece, k) => {
      const path = piece.path.map((q): Pt => { const u = turnOver(row, q); return [u[0] + o[0], u[1] + o[1]] })
      const of = (base: string) => (k ? `${base} fb-row-piece-${Math.min(k, 3)}` : base)
      handles.push(<polyline key={`path-${k}`} className={of('fb-row-path')} points={path.map((q) => { const p = at(q); return `${p.x},${p.y}` }).join(' ')} />)
      if (!draft) {
        path.slice(1).forEach((q, i) => {
          const m = at([(path[i][0] + q[0]) / 2, (path[i][1] + q[1]) / 2])
          handles.push(
            <g key={`add-${k}-${i}`} className="fb-row-add-point" data-handle="add-point" data-piece={k} data-leg={i} role="button" aria-label={t('blockRows.addPoint', { name })}
              onPointerDown={(e) => { if (e.button !== 0) return; e.stopPropagation(); e.preventDefault(); done(withPiecePath(row, k, addPoint(pathOf(k), i))) }}>
              <circle cx={m.x} cy={m.y} r={r6} />
              <path d={`M${m.x - r6 * 0.55},${m.y}H${m.x + r6 * 0.55}M${m.x},${m.y - r6 * 0.55}V${m.y + r6 * 0.55}`} />
            </g>,
          )
        })
      }
      path.forEach((q, i) => {
        const p = at(q)
        handles.push(
          <circle key={`pt-${k}-${i}`} className={of('fb-row-shape-handle')} data-handle="point" data-piece={k} data-point={i} cx={p.x} cy={p.y} r={r6} role="button"
            aria-label={k ? t('blockRows.piecePointHandle', { name, piece: k + 1, n: i + 1 }) : t('blockRows.pointHandle', { name, n: i + 1 })}
            onPointerDown={(e) => start(e, { kind: 'point', i, k })} {...handlers}
            onDoubleClick={(e) => { e.stopPropagation(); done(withPiecePath(row, k, dropPoint(pathOf(k), i)), k === 0 && i === 0) }} />,
        )
      })
    })
  }
  if (!handles.length) return null
  return (
    <g className="fb-edit-handles fb-row-shapes" transform={`rotate(${shape.rotation} ${shape.cx} ${shape.cy})`}>
      {preview?.map((q, i) => { const p = at(q); return <rect key={`ghost-${i}`} className="fb-row-ghost" x={p.x - cell * 0.45} y={p.y - cell * 0.45} width={cell * 0.9} height={cell * 0.9} rx={4} /> })}
      {handles}
    </g>
  )
}
