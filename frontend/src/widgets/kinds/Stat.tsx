import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import type { Level } from '../level'
import { useNumberStyle } from './display'
import { clock } from '@/lib/time'
import { changeOf, formatValue, linesOf, type Look, stateCounts, statOf } from './shape'
import { Graph, Plot } from './Graph'

const toneClass = (tone: string) => (tone ? ` fb-tone-${tone}` : '')

/** One number, as big as the box allows. Medium adds how it is made up; large adds its history. */
export function StatKind({ widget, level, box, look = {} }: { widget: Widget; level: Level; box: { w: number; h: number }; look?: Look }) {
  const { t, i18n } = useTranslation()
  const style = useNumberStyle()
  const s = statOf(widget, i18n.language, style)
  const counts = stateCounts(widget)
  const { lines } = linesOf(widget)
  const graphH = level === 'l' && lines.length ? Math.round(box.h * 0.45) : 0
  // Below large, where the full graph doesn't fit, the pane may ask for its history as a sparkline.
  const real = lines.filter((l) => !l.ghost)
  const sparkH = look.spark && !graphH && real.some((l) => l.points.length > 1) ? Math.max(16, Math.min(60, Math.round(box.h * 0.25))) : 0
  const change = look.change ? changeOf(widget) : null
  const moved = (c: NonNullable<typeof change>) => {
    const arrow = c.to > c.from ? '▲' : c.to < c.from ? '▼' : '='
    const by = c.pct != null ? `${Math.abs(c.pct).toLocaleString(i18n.language, { maximumFractionDigits: Math.abs(c.pct) < 10 ? 1 : 0 })} %`
      : (() => { const f = formatValue(Math.abs(c.to - c.from), linesOf(widget).unit, i18n.language, style); return `${f.value}${f.unit ? ` ${f.unit}` : ''}` })()
    const since = c.hour ? t('widgets.kind.changeHour') : c.at != null ? t('widgets.kind.changeSince', { time: clock(c.at) }) : t('widgets.kind.changeStart')
    return { arrow, by, since }
  }
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
      {change && (() => {
        const m = moved(change)
        return <div className="fb-w-change"><b>{m.arrow} {m.by}</b> {m.since}</div>
      })()}
      {sparkH > 0 && <div className="fb-w-spark"><Plot lines={real.slice(0, 1)} stack="none" area={false} w={box.w} h={sparkH} /></div>}
      {graphH > 40 && <Graph widget={widget} level="m" box={{ w: box.w, h: graphH }} />}
    </div>
  )
}
