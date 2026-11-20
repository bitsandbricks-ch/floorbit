import { IconArrowDownRight, IconArrowUpRight, IconMinus } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Sparkline } from '@/widgets/Sparkline'

export type StatTone = 'up' | 'warn' | 'down'

/** One figure (#1019): the same tile on every page, and what the dashboard's Stat widget renders.
 *  Value with its unit and tone, "of N", a line under it, a trend over the last samples, the change
 *  since before (its arrow coloured by whether that is good), and a size. */
export function StatTile({ label, value, unit, of, sub, tone, trend, trendLabel, change, size = 'm', href }: {
  label: string
  value: string | number
  unit?: string
  /** "of 48": the whole the value is part of. */
  of?: number | null
  sub?: string
  tone?: StatTone
  /** Oldest first; two or more points draw a line. */
  trend?: number[]
  trendLabel?: string
  /** The change since before; ``goodWhen`` colours the arrow (more errors is bad, more seats online good). */
  change?: { value: number; unit?: string; goodWhen?: 'up' | 'down' }
  size?: 's' | 'm' | 'l'
  /** Where it drills down to, usually the floor plan. */
  href?: string
}) {
  const { t } = useTranslation()
  const spark = !!trend && trend.length > 1
  const more = sub || spark || change
  const tile = (
    <dl className={`fb-stat fb-stat-${size}${tone ? ` fb-stat-${tone}` : ''}`}>
      <dt>{label}</dt>
      <dd>
        {value}
        {unit && <small className="fb-stat-unit"> {unit}</small>}
        {of != null && <small className="fb-stat-unit"> {t('stat.of', { count: of })}</small>}
      </dd>
      {/* A <dl> may only hold dt and dd, so the line under the figure, the change and the trend share a second dd (axe). */}
      {more && (
        <dd className="fb-stat-more">
          {change && <Change {...change} />}
          {sub && <span>{sub}</span>}
          {spark && (
            <span className="fb-stat-spark" role="img" aria-label={t('stat.trend', { name: trendLabel ?? label })}>
              <Sparkline points={trend!} />
            </span>
          )}
        </dd>
      )}
    </dl>
  )
  return href ? <a className="fb-stat-link" href={href}>{tile}</a> : tile
}

function Change({ value, unit, goodWhen }: { value: number; unit?: string; goodWhen?: 'up' | 'down' }) {
  const { t } = useTranslation()
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : 'flat'
  const Icon = dir === 'up' ? IconArrowUpRight : dir === 'down' ? IconArrowDownRight : IconMinus
  const tone = dir === 'flat' || !goodWhen ? '' : dir === goodWhen ? ' fb-tone-up' : ' fb-tone-down'
  const text = `${value > 0 ? '+' : value < 0 ? '−' : '±'}${Math.abs(value).toLocaleString()}${unit ?? ''}`
  return (
    <span className={`fb-stat-change${tone}`} aria-label={t(`stat.change.${dir}`, { value: text })}>
      <Icon size={14} aria-hidden /> {text}
    </span>
  )
}
