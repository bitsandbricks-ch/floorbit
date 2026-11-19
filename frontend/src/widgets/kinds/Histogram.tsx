import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import type { Level } from '../level'
import { binsOf, formatValue, linesOf, valuesOf } from './shape'
import { StatKind } from './Stat'

/** How values spread: ranges of a round width along the bottom, how many fall in each as the
 *  height. Hover a column for its range and count. */
export function HistogramKind({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const [hot, setHot] = useState<number | null>(null)
  if (level === 's') return <StatKind widget={widget} level={level} box={box} />
  const values = valuesOf(widget)
  const bins = binsOf(values, Math.max(2, Math.min(30, Math.floor(box.w / 22))))
  if (!bins.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const unit = widget.type === 'series' || widget.type === 'sparkline' ? linesOf(widget).unit : ''
  const fmt = (v: number) => formatValue(v, unit, i18n.language)
  const range = (b: { from: number; to: number }) => { const a = fmt(b.from), z = fmt(b.to); return `${a.value}–${z.value}${z.unit ? ` ${z.unit}` : ''}` }
  const top = Math.max(1, ...bins.map((b) => b.count))
  const plotH = box.h - 18 - 16 - (level === 'l' ? 18 : 0)
  const focus = hot != null ? bins[hot] : null
  return (
    <div className="fb-w-cols-wrap" onPointerLeave={() => setHot(null)}>
      <div className="fb-w-cols fb-w-hist" role="img"
        aria-label={t('widgets.kind.histogramLabel', { name: widget.label, count: values.length })}>
        {bins.map((b, i) => (
          <div key={i} className={`fb-w-col${hot === i ? ' hot' : ''}`} title={t('widgets.kind.binTip', { range: range(b), count: b.count })}
            onPointerEnter={() => setHot(i)}>
            <span className="fb-w-col-value">{level === 'l' || bins.length <= 12 ? b.count : ''}</span>
            <span className="fb-w-col-track" style={{ height: plotH }}>
              <span className="fb-w-col-fill" style={{ height: `${(b.count / top) * 100}%`, background: 'var(--color-trace)' }} />
            </span>
          </div>
        ))}
      </div>
      <div className="fb-w-axis">
        <span>{fmt(bins[0].from).value}</span>
        <span>{focus ? t('widgets.kind.binTip', { range: range(focus), count: focus.count }) : t('widgets.kind.values', { count: values.length })}</span>
        <span>{`${fmt(bins[bins.length - 1].to).value}${fmt(bins[bins.length - 1].to).unit ? ` ${fmt(bins[bins.length - 1].to).unit}` : ''}`}</span>
      </div>
    </div>
  )
}
