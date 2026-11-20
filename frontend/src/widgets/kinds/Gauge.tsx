import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import type { Level } from '../level'
import { useNumberStyle } from './display'
import { formatValue, scaleOf, statOf } from './shape'

const SWEEP = 240 // degrees: open at the bottom, like a dial

/** A value on its scale as a dial: a stat with a max, or a sparkline's latest reading. */
export function GaugeKind({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const style = useNumberStyle()
  const scale = scaleOf(widget)
  if (!scale) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const s = statOf(widget, i18n.language, style)
  const share = Math.min(1, Math.max(0, (scale.value - scale.min) / (scale.max - scale.min || 1)))
  // The dial is 100 × 86 units plus half a stroke on each side: keep all of it inside the box.
  const size = Math.max(40, Math.min(box.w, box.h / 0.86) * 0.9)
  const r = 42, c = 50
  const arc = (from: number, to: number) => {
    const p = (deg: number) => {
      const a = ((deg - 90 - SWEEP / 2) * Math.PI) / 180
      return `${(c + r * Math.cos(a)).toFixed(2)} ${(c + r * Math.sin(a)).toFixed(2)}`
    }
    return `M ${p(from)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${p(to)}`
  }
  const tone = s.tone || (share >= 0.9 ? 'ok' : '')
  const fmt = (v: number) => formatValue(v, '', i18n.language, style).value
  const label = t('widgets.kind.gaugeLabel', { value: s.value, max: fmt(scale.max), pct: Math.round(share * 100) })
  return (
    <div className="fb-w-gauge" title={label}>
      <svg width={size} height={size * 0.86} viewBox="0 0 100 86" role="img" aria-label={label}>
        <path className="fb-w-gauge-track" d={arc(0, SWEEP)} />
        {share > 0 && <path className={`fb-w-gauge-fill${tone ? ` fb-tone-${tone}` : ''}`} d={arc(0, Math.max(1, SWEEP * share))} />}
        <text x={50} y={level === 's' ? 56 : 52} className="fb-w-gauge-value">{s.value}</text>
        {level !== 's' && <text x={50} y={66} className="fb-w-gauge-unit">{`${Math.round(share * 100)} %`}</text>}
        {level === 'l' && (
          <>
            <text x={14} y={84} className="fb-w-gauge-end">{fmt(scale.min)}</text>
            <text x={86} y={84} className="fb-w-gauge-end">{fmt(scale.max)}</text>
          </>
        )}
      </svg>
    </div>
  )
}
