import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import type { Level } from '../level'
import { useNumberStyle } from './display'
import { linesOf, stateCounts, statOf } from './shape'
import { Graph } from './Graph'

const toneClass = (tone: string) => (tone ? ` fb-tone-${tone}` : '')

/** One number, as big as the box allows. Medium adds how it is made up; large adds its history. */
export function StatKind({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const style = useNumberStyle()
  const s = statOf(widget, i18n.language, style)
  const counts = stateCounts(widget)
  const { lines } = linesOf(widget)
  const graphH = level === 'l' && lines.length ? Math.round(box.h * 0.45) : 0
  const full = `${s.value}${s.unit ? ` ${s.unit}` : ''}${s.of != null ? ` / ${s.of}` : ''}`
  return (
    <div className="fb-w-stat">
      <div className="fb-w-stat-main" title={full}>
        <span className={`fb-w-stat-value${toneClass(s.tone)}`}>{s.value}</span>
        {s.unit && <span className="fb-w-stat-unit">{s.unit}</span>}
        {s.of != null && <span className="fb-w-stat-unit">{t('widgets.kind.of', { count: s.of })}</span>}
      </div>
      {level !== 's' && counts.length > 0 && (
        <div className="fb-w-counts">
          {counts.map(([state, n]) => (
            <span key={state} title={t(`widgets.state.${state}`)}>
              <span className={`fb-dot ${state}`} role="img" aria-label={t(`widgets.state.${state}`)} /> {n}
            </span>
          ))}
        </div>
      )}
      {graphH > 40 && <Graph widget={widget} level="m" box={{ w: box.w, h: graphH }} />}
    </div>
  )
}
