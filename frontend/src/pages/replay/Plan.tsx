import type { PlanDrawing } from '@/api/types'
import { chartPath } from './model'
import { MiniPlan } from '@/components/MiniPlan'

export const CHART_W = 1000
export const CHART_H = 120

/** The hall's seat blocks: seats that were on filled, open incidents ringed. */
export function Plan({ drawing, on, rings, label }: { drawing: PlanDrawing; on: Set<string>; rings: Set<string>; label: string }) {
  return (
    <MiniPlan drawing={drawing} label={label} className="fb-replay-plan" frames
      seat={(id, at) => ({
        className: on.has(id) ? 'on' : undefined,
        children: rings.has(id) ? <circle className="ring" cx={at.x} cy={at.y} r={drawing.cell * 0.9} /> : undefined,
      })} />
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
