import type { CSSProperties } from 'react'
import type { PlanDrawing, PlanMark } from '@/api/types'
import { type LayerId, type LayerState, LAYERS, MARK_LAYER, opacity } from './layers'
import { markPx } from './markSize'

const layerOf = (m: PlanMark): LayerId => MARK_LAYER[m.layer ?? 'overview'] ?? 'marks'

/** Walls, zones, labels and icons (floorbit/plan_marks.py), drawn under the seats. With ``layers``,
 *  each mark shows only while its layer is on, faded with it. */
export function PlanMarks({ drawing, layers }: { drawing: PlanDrawing; layers?: LayerState }) {
  const marks = (drawing.marks ?? []).filter((m) => !layers || layers.on.has(layerOf(m)))
  if (!marks.length) return null
  const order = (m: PlanMark) => ({ zone: 0, wall: 1, text: 2, icon: 3 })[m.kind]
  return (
    <g className="fb-marks" aria-hidden="true">
      <CustomIconMasks icons={drawing.custom_icons} />
      {LAYERS.map((id) => {
        const mine = marks.filter((m) => layerOf(m) === id)
        if (!mine.length) return null
        return (
          <g key={id} data-layer={id} opacity={layers ? opacity(layers, id) : undefined}>
            {mine.sort((a, b) => (a.z ?? 0) - (b.z ?? 0) || order(a) - order(b)).map((m, i) => <Mark key={i} m={m} icons={drawing.icons ?? {}} custom={drawing.custom_icons ?? {}} />)}
          </g>
        )
      })}
    </g>
  )
}

/** Uploaded icons are images (never inline markup); an alpha mask paints each in the icon's colour.
 *  The masks scale to whatever uses them, so one per icon serves every mark. */
function CustomIconMasks({ icons }: { icons?: Record<string, string> }) {
  const all = Object.entries(icons ?? {})
  if (!all.length) return null
  return (
    <defs>
      {all.map(([id, uri]) => (
        <mask key={id} id={maskId(id)} maskContentUnits="objectBoundingBox" style={{ maskType: 'alpha' }}>
          <image href={uri} width={1} height={1} />
        </mask>
      ))}
    </defs>
  )
}

const maskId = (icon: string) => `fbi-${icon}`

function Mark({ m, icons, custom }: { m: PlanMark; icons: Record<string, string[]>; custom: Record<string, string> }) {
  // A picked colour wins over the theme's; without one the stylesheet's light or dark colour shows.
  const tint = m.tint ? { stroke: m.tint } : undefined
  const turn = (x: number, y: number) => (m.rotation ? `rotate(${m.rotation} ${x} ${y})` : undefined)
  switch (m.kind) {
    case 'zone':
      return (
        <g className={`zone zone-${m.color ?? 'muted'}`} style={m.tint ? ({ '--zone': m.tint } as CSSProperties) : undefined} transform={m.rotation ? `rotate(${m.rotation} ${m.x + (m.w ?? 0) / 2} ${m.y + (m.h ?? 0) / 2})` : undefined}>
          <rect x={m.x} y={m.y} width={m.w} height={m.h} rx={10} />
          {m.label && <text x={m.x + 14} y={m.y + 30} fontSize={24}>{m.label}</text>}
        </g>
      )
    case 'wall':
      return m.points?.length
        ? <polyline className={`wall${m.style === 'dashed' ? ' dashed' : ''}`} style={tint} points={[[m.x, m.y], ...m.points, [m.x2, m.y2]].join(' ')} />
        : <line className={`wall${m.style === 'dashed' ? ' dashed' : ''}`} style={tint} x1={m.x} y1={m.y} x2={m.x2} y2={m.y2} />
    case 'text':
      return (
        <text className="label" style={m.tint ? { fill: m.tint } : undefined} x={m.x} y={m.y} dy="0.35em" fontSize={markPx(m)} transform={turn(m.x, m.y)}>{m.text}</text>
      )
    case 'icon': {
      const s = markPx(m)
      const paths = icons[m.icon ?? '']
      const upload = !paths && custom[m.icon ?? '']
      if (!paths && !upload) return null
      return (
        <g className="icon" style={m.tint ? ({ '--tint': m.tint } as CSSProperties) : undefined} transform={`translate(${m.x - s / 2} ${m.y - s / 2})`}>
          <rect width={s} height={s} rx={s / 4} />
          <svg x={s * 0.15} y={s * 0.15} width={s * 0.7} height={s * 0.7} viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <g transform={m.rotation ? `rotate(${m.rotation} 12 12)` : undefined}>
              {paths ? paths.map((d, i) => <path key={i} d={d} />)
                : <path d="M0 0H24V24H0Z" fill="currentColor" stroke="none" mask={`url(#${maskId(m.icon ?? '')})`} />}
            </g>
          </svg>
        </g>
      )
    }
  }
}
