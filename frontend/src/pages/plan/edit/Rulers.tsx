import type { OverlayContext } from '../SeatMap'
import { RULER_BAND as BAND, rulerSteps, seatsLabel, useRulerPointer } from './rulers'

/** Rulers along the plan's top and left edges, in seats (one grid cell each) from the plan's corner,
 *  the unit the wall and zone tools measure in. They follow pan and zoom, and mark where the pointer
 *  is, or while dragging the middle of what is dragged (``at``, Mike). */
export function Rulers({ ctx, cell, at }: { ctx: OverlayContext; cell: number; at?: { x: number; y: number } | null }) {
  const { shown, scale } = ctx
  const pointer = useRulerPointer()
  const mark = at ?? pointer
  const px = 1 / scale
  const { major, minor } = rulerSteps(cell * scale)
  const band = BAND * px
  const ticks = (from: number, to: number) => {
    const out: number[] = []
    for (let n = Math.ceil(from / cell / minor) * minor; n * cell <= to; n += minor) out.push(n)
    return out
  }
  const xs = ticks(shown.x + band, shown.x + shown.w)
  const ys = ticks(shown.y + band, shown.y + shown.h)
  const len = (n: number) => (n % major === 0 ? 8 : 4) * px
  return (
    <g className="fb-edit-rulers" pointerEvents="none" aria-hidden="true">
      <rect x={shown.x} y={shown.y} width={shown.w} height={band} />
      <rect x={shown.x} y={shown.y} width={band} height={shown.h} />
      {xs.map((n) => (
        <g key={`x${n}`}>
          <line x1={n * cell} x2={n * cell} y1={shown.y + band} y2={shown.y + band - len(n)} vectorEffect="non-scaling-stroke" />
          {n % major === 0 && <text x={n * cell + 3 * px} y={shown.y + 10 * px} fontSize={10 * px}>{n}</text>}
        </g>
      ))}
      {ys.map((n) => (
        <g key={`y${n}`}>
          <line y1={n * cell} y2={n * cell} x1={shown.x + band} x2={shown.x + band - len(n)} vectorEffect="non-scaling-stroke" />
          {n % major === 0 && (
            <text x={shown.x + 10 * px} y={n * cell - 3 * px} fontSize={10 * px} transform={`rotate(-90 ${shown.x + 10 * px} ${n * cell - 3 * px})`}>{n}</text>
          )}
        </g>
      ))}
      {mark && mark.x > shown.x + band && mark.x < shown.x + shown.w && (
        <g className="mark">
          <line x1={mark.x} x2={mark.x} y1={shown.y} y2={shown.y + band} vectorEffect="non-scaling-stroke" />
          <text x={mark.x + 3 * px} y={shown.y + 10 * px} fontSize={10 * px}>{seatsLabel(mark.x, cell)}</text>
        </g>
      )}
      {mark && mark.y > shown.y + band && mark.y < shown.y + shown.h && (
        <g className="mark">
          <line y1={mark.y} y2={mark.y} x1={shown.x} x2={shown.x + band} vectorEffect="non-scaling-stroke" />
          <text x={shown.x + 10 * px} y={mark.y - 3 * px} fontSize={10 * px} transform={`rotate(-90 ${shown.x + 10 * px} ${mark.y - 3 * px})`}>{seatsLabel(mark.y, cell)}</text>
        </g>
      )}
      <rect className="corner" x={shown.x} y={shown.y} width={band} height={band} />
    </g>
  )
}
