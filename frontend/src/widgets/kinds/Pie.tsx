import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { State, Widget } from '@/api/types'
import type { Level } from '../level'
import { useNumberStyle } from './display'
import { formatValue, partsOf, slices } from './shape'

/** A donut of how a whole splits up: states, or a list's numbers (seven slices at most). Hover a
 *  slice or its legend row for its count and share. */
export function PieKind({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const [hot, setHot] = useState<number | null>(null)
  const style = useNumberStyle()
  const parts = slices(partsOf(widget, (s: State) => t(`widgets.state.${s}`), i18n.language, true), t('widgets.kind.other'), i18n.language)
  const total = parts.reduce((a, p) => a + p.value, 0)
  if (!total) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const legend = level !== 's'
  const size = Math.max(40, Math.min(box.h, legend ? box.w * 0.5 : box.w))
  const pct = (v: number) => Math.round((v / total) * 100)
  const r = 40, c = 50, ring = 2 * Math.PI * r
  // Where each slice starts along the ring: the sum of the slices before it.
  const starts = parts.map((_, i) => parts.slice(0, i).reduce((a, p) => a + (p.value / total) * ring, 0))
  const focus = hot != null ? parts[hot] : null
  return (
    <div className={`fb-w-pie${legend ? '' : ' small'}`} onPointerLeave={() => setHot(null)}>
      <svg width={size} height={size} viewBox="0 0 100 100" role="img"
        aria-label={t('widgets.kind.pieLabel', { parts: parts.map((p) => `${p.label} ${p.text}`).join(', ') })}>
        <g transform="rotate(-90 50 50)">
        {parts.map((p, i) => {
          const len = (p.value / total) * ring
          return (
            <circle key={i} cx={c} cy={c} r={r} className={`fb-w-slice${hot === i ? ' hot' : ''}`} stroke={p.colour}
              strokeDasharray={`${Math.max(0, len - (parts.length > 1 ? 1 : 0))} ${ring}`} strokeDashoffset={-starts[i]}
              onPointerEnter={() => setHot(i)}>
              <title>{`${p.label}: ${p.text} (${pct(p.value)} %)`}</title>
            </circle>
          )
        })}
        </g>
        <text x={50} y={focus ? 50 : 55} className="fb-w-pie-total">{focus ? focus.text : centre(total, i18n.language, style)}</text>
        {focus && <text x={50} y={64} className="fb-w-pie-sub">{`${pct(focus.value)} %`}</text>}
      </svg>
      {legend && (
        <ul className="fb-w-pie-legend">
          {parts.map((p, i) => (
            <li key={i} className={hot === i ? 'hot' : undefined} onPointerEnter={() => setHot(i)}>
              <i style={{ background: p.colour }} />
              <span>{p.label}</span>
              <b>{p.text}</b>
              {level === 'l' && <em>{pct(p.value)} %</em>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The whole in the middle of the ring: short (1.1T, not 1,105,774,540,503), so it fits. */
function centre(total: number, lang: string, style: { decimals?: number; short?: boolean }) {
  // Spread would let an unset ``short`` (undefined) switch it back off.
  return formatValue(total, '', lang, { short: true, decimals: style.decimals }).value
}
