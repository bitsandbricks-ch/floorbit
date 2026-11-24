import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { normalizeTone, StatTile } from '@bitsandbricks/ui'
import type { Level } from '../level'
import { useNumberStyle } from './display'
import { clock } from '@/lib/time'
import { changeOf, formatValue, linesOf, type Look, stateCounts, statOf } from './shape'
import { Graph } from './Graph'

/** One number, as big as the box allows, drawn by the same StatTile as every page (#1154).
 *  Medium adds how it is made up; large adds its history. */
export function StatKind({ widget, level, box, look = {} }: { widget: Widget; level: Level; box: { w: number; h: number }; look?: Look }) {
  const { t, i18n } = useTranslation()
  const style = useNumberStyle()
  const s = statOf(widget, i18n.language, style)
  const counts = stateCounts(widget)
  const { lines, unit } = linesOf(widget)
  const graphH = level === 'l' && lines.length ? Math.round(box.h * 0.45) : 0
  // Below large, where the full graph doesn't fit, the pane may ask for its history as a sparkline.
  const real = lines.find((l) => !l.ghost && l.points.length > 1)
  const trend = look.spark && !graphH && real ? real.points.map((p) => p[1]) : undefined
  const c = look.change ? changeOf(widget) : null
  const change = c ? (() => {
    const by = c.pct != null
      ? `${Math.abs(c.pct).toLocaleString(i18n.language, { maximumFractionDigits: Math.abs(c.pct) < 10 ? 1 : 0 })} %`
      : (() => { const f = formatValue(Math.abs(c.to - c.from), unit, i18n.language, style); return `${f.value}${f.unit ? ` ${f.unit}` : ''}` })()
    const since = c.hour ? t('widgets.kind.changeHour') : c.at != null ? t('widgets.kind.changeSince', { time: clock(c.at) }) : t('widgets.kind.changeStart')
    return { value: c.to - c.from, text: by, since }
  })() : undefined
  const extra = level !== 's' && counts.length > 0 ? (
    <span className="fb-w-counts">
      {counts.map(([state, n]) => (
        <span key={state} title={t(`widgets.state.${state}`)}>
          <span className={`fb-dot ${state}`} role="img" aria-label={t(`widgets.state.${state}`)} /> {n}
        </span>
      ))}
    </span>
  ) : undefined
  return (
    <div className="fb-w-stat">
      <StatTile size="fit" hideLabel label={widget.label} value={s.value} unit={s.unit || undefined} of={s.of}
        tone={normalizeTone(s.tone)} trend={trend} change={change} extra={extra} />
      {graphH > 40 && <Graph widget={widget} level="m" box={{ w: box.w, h: graphH }} />}
    </div>
  )
}
