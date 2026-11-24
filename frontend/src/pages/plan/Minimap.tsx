import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanBlock, PlanDrawing } from '@/api/types'
import { blockAlarm } from './blockTop'
import { blockSums } from './blockSums'
import { centreOn } from './minimap'
import type { View } from './model'

/** A small overview of the whole hall in the corner while zoomed in: the blocks, the part on
 *  screen as a frame, and a click or drag on it moves there. */
export function Minimap({ drawing, blocks, view, fit, setView }: {
  drawing: PlanDrawing; blocks: PlanBlock[]; view: View; fit: View; setView: (v: View) => void
}) {
  const { t } = useTranslation()
  const svg = useRef<SVGSVGElement>(null)
  const dragging = useRef(false)
  const to = (e: React.PointerEvent) => {
    const box = svg.current?.getBoundingClientRect()
    if (!box || !box.width) return
    const x = fit.x + ((e.clientX - box.left) / box.width) * fit.w
    const y = fit.y + ((e.clientY - box.top) / box.height) * fit.h
    setView(centreOn(view, { x, y }))
  }
  const width = 180
  const sums = blockSums(drawing.shapes, blocks)
  return (
    <svg ref={svg} className="fb-minimap fb-no-print" role="img" aria-label={t('plan.minimap')}
      viewBox={`${fit.x} ${fit.y} ${fit.w} ${fit.h}`} width={width} height={(width * fit.h) / fit.w} preserveAspectRatio="none"
      onPointerDown={(e) => { e.stopPropagation(); dragging.current = true; e.currentTarget.setPointerCapture?.(e.pointerId); to(e) }}
      onPointerMove={(e) => { if (dragging.current) to(e) }}
      onPointerUp={() => { dragging.current = false }}>
      <rect className="bg" x={fit.x} y={fit.y} width={fit.w} height={fit.h} />
      {drawing.shapes.map((b, i) => (
        <rect key={i} className={blockAlarm(sums[i]) ? 'blk alarm' : 'blk'}
          x={-b.w / 2} y={-b.h / 2} width={b.w} height={b.h} transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`} />
      ))}
      <rect className="view" x={view.x} y={view.y} width={view.w} height={view.h} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
