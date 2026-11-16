import type { PlanDrawing, PlanMark } from '@/api/types'
import { type LayerId, type LayerState, LAYERS, MARK_LAYER, opacity } from './layers'

// Sizes in drawing units (the plan is 1600 wide, a seat 32).
const TEXT = { s: 20, m: 28, l: 44 }
const ICON = { s: 26, m: 36, l: 52 }

const layerOf = (m: PlanMark): LayerId => MARK_LAYER[m.layer ?? 'overview'] ?? 'marks'

/** Walls, zones, labels and icons (floorbit/plan_marks.py), drawn under the seats. With ``layers``,
 *  each mark shows only while its layer is on, faded with it. */
export function PlanMarks({ drawing, layers }: { drawing: PlanDrawing; layers?: LayerState }) {
  const marks = (drawing.marks ?? []).filter((m) => !layers || layers.on.has(layerOf(m)))
  if (!marks.length) return null
  const order = (m: PlanMark) => ({ zone: 0, wall: 1, text: 2, icon: 3 })[m.kind]
  return (
    <g className="fb-marks" aria-hidden="true">
      {LAYERS.map((id) => {
        const mine = marks.filter((m) => layerOf(m) === id)
        if (!mine.length) return null
        return (
          <g key={id} data-layer={id} opacity={layers ? opacity(layers, id) : undefined}>
            {mine.sort((a, b) => (a.z ?? 0) - (b.z ?? 0) || order(a) - order(b)).map((m, i) => <Mark key={i} m={m} icons={drawing.icons ?? {}} />)}
          </g>
        )
      })}
    </g>
  )
}

function Mark({ m, icons }: { m: PlanMark; icons: Record<string, string[]> }) {
  const turn = (x: number, y: number) => (m.rotation ? `rotate(${m.rotation} ${x} ${y})` : undefined)
  switch (m.kind) {
    case 'zone':
      return (
        <g className={`zone zone-${m.color ?? 'muted'}`}>
          <rect x={m.x} y={m.y} width={m.w} height={m.h} rx={10} />
          {m.label && <text x={m.x + 14} y={m.y + 30} fontSize={24}>{m.label}</text>}
        </g>
      )
    case 'wall':
      return <line className={`wall${m.style === 'dashed' ? ' dashed' : ''}`} x1={m.x} y1={m.y} x2={m.x2} y2={m.y2} />
    case 'text':
      return (
        <text className="label" x={m.x} y={m.y} dy="0.35em" fontSize={TEXT[m.size ?? 'm']} transform={turn(m.x, m.y)}>{m.text}</text>
      )
    case 'icon': {
      const s = ICON[m.size ?? 'm']
      const paths = icons[m.icon ?? '']
      if (!paths) return null
      return (
        <g className="icon" transform={`translate(${m.x - s / 2} ${m.y - s / 2})`}>
          <rect width={s} height={s} rx={s / 4} />
          <svg x={s * 0.15} y={s * 0.15} width={s * 0.7} height={s * 0.7} viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <g transform={m.rotation ? `rotate(${m.rotation} 12 12)` : undefined}>
              {paths.map((d, i) => <path key={i} d={d} />)}
            </g>
          </svg>
        </g>
      )
    }
  }
}
