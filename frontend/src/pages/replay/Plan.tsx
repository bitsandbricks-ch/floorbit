import type { PlanDrawing } from '@/api/types'
import { chartPath } from './model'

export const CHART_W = 1000
export const CHART_H = 120

/** The hall's seat blocks: seats that were on filled, open incidents ringed. */
export function Plan({ drawing, on, rings, label }: { drawing: PlanDrawing; on: Set<string>; rings: Set<string>; label: string }) {
  return (
    <svg viewBox={drawing.box} role="img" aria-label={label} className="fb-replay-plan">
      {drawing.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            <rect className="blk" x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={6} />
            {b.cells.map((c) => (
              <g key={c.seat}>
                <rect className={on.has(c.seat) ? 'cell on' : 'cell'} data-seat={c.seat} x={c.x + 1} y={c.y + 1}
                  width={drawing.cell - 2} height={drawing.cell - 2} rx={3}>
                  <title>{c.seat}</title>
                </rect>
                {rings.has(c.seat) && <circle className="ring" cx={c.x + drawing.cell / 2} cy={c.y + drawing.cell / 2} r={drawing.cell * 0.9} />}
              </g>
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={b.cy - Math.max(b.w, b.h) / 2 - 18}>{b.name}</text>}
        </g>
      ))}
    </svg>
  )
}

/** Bandwidth over time, with the peak and a cursor; a click jumps there. */
export function Chart({ samples, peak, start, end, t, onSeek, label }: {
  samples: { t: number; down: number; up: number }[]; peak: { at: number } | null
  start: number; end: number; t: number; onSeek: (t: number) => void; label: string
}) {
  const span = Math.max(1, end - start)
  const x = (ts: number) => ((ts - start) / span) * CHART_W
  const line = chartPath({ samples }, start, end, CHART_W, CHART_H)
  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} preserveAspectRatio="none" className="fb-replay-chart" role="img" aria-label={label}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect()
        onSeek(start + ((e.clientX - box.left) / box.width) * span)
      }}>
      {line && <path d={`${line} L${CHART_W},${CHART_H} L0,${CHART_H} Z`} className="area" />}
      {line && <path d={line} className="line" />}
      {peak && peak.at >= start && <line className="peak" x1={x(peak.at)} x2={x(peak.at)} y1={0} y2={CHART_H} />}
      <line className="cursor" x1={x(t)} x2={x(t)} y1={0} y2={CHART_H} />
    </svg>
  )
}
