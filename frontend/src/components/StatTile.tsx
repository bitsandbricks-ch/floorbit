import type { ReactNode } from 'react'
import { IconArrowDownRight, IconArrowUpRight, IconMinus } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Sparkline } from '@/widgets/Sparkline'

export type StatTone = 'up' | 'warn' | 'down'

/** One figure (#1019): the same tile on every page, and what the dashboard's Stat widget renders.
 *  Value with its unit and tone, "of N", a line under it, a trend over the last samples, the change
 *  since before (its arrow coloured by whether that is good), and a size. */
export function StatTile({ label, value, unit, of, sub, tone, trend, trendLabel, change, size = 'm', href, hideLabel, extra }: {
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
  change?: Change
  /** ``fit``: inside a dashboard pane, which is the card; the figure grows with the pane and the tone colours it. */
  size?: 's' | 'm' | 'l' | 'fit'
  /** Where it drills down to, usually the floor plan. */
  href?: string
  /** The label stays for screen readers only, where a pane's title already shows it. */
  hideLabel?: boolean
  /** More under the figure, such as how many are up, down or waiting. */
  extra?: ReactNode
}) {
  const { t } = useTranslation()
  const spark = !!trend && trend.length > 1
  const more = sub || spark || change || extra
  const full = `${value}${unit ? ` ${unit}` : ''}${of != null ? ` / ${of}` : ''}`
  const tile = (
    <dl className={`fb-stat fb-stat-${size}${tone ? ` fb-stat-${tone}` : ''}`}>
      <dt className={hideLabel ? 'fb-sr-only' : undefined}>{label}</dt>
      <dd title={size === 'fit' ? full : undefined}>
        {value}
        {unit && <small className="fb-stat-unit"> {unit}</small>}
        {of != null && <small className="fb-stat-unit"> {t('stat.of', { count: of })}</small>}
      </dd>
      {/* A <dl> may only hold dt and dd, so the line under the figure, the change and the trend share a second dd (axe). */}
      {more && (
        <dd className="fb-stat-more">
          {extra}
          {change && <ChangeArrow {...change} />}
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

export interface Change {
  value: number
  unit?: string
  goodWhen?: 'up' | 'down'
  /** The change as it reads, when the number alone would lose its unit's scale (``1.2 Gbit/s``). */
  text?: string
  /** Since when, after the change (``since 07:24``). */
  since?: string
}

function ChangeArrow({ value, unit, goodWhen, text: shown, since }: Change) {
  const { t } = useTranslation()
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : 'flat'
  const Icon = dir === 'up' ? IconArrowUpRight : dir === 'down' ? IconArrowDownRight : IconMinus
  const tone = dir === 'flat' || !goodWhen ? '' : dir === goodWhen ? ' fb-tone-up' : ' fb-tone-down'
  const text = `${value > 0 ? '+' : value < 0 ? '−' : '±'}${shown ?? `${Math.abs(value).toLocaleString()}${unit ?? ''}`}`
  return (
    <span className={`fb-stat-change${tone}`} aria-label={`${t(`stat.change.${dir}`, { value: text })}${since ? ` ${since}` : ''}`}>
      <Icon size="1em" aria-hidden /> <b>{text}</b>{since && <> {since}</>}
    </span>
  )
}
