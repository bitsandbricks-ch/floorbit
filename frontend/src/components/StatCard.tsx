/** One figure on a dashboard (issue #103): the same card on Stats, Wi-Fi, Health and Problems, with
 *  an optional trend line over the last samples and a link to drill down (usually the floor plan). */
export function StatCard({ label, value, sub, trend, tone, href, trendLabel }: {
  label: string
  value: string
  sub?: string
  /** Oldest first; two or more points draw a line. */
  trend?: number[]
  tone?: 'up' | 'warn' | 'down'
  href?: string
  trendLabel?: string
}) {
  const card = (
    <dl className={`fb-stat${tone ? ` fb-stat-${tone}` : ''}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
      {sub && <span>{sub}</span>}
      {trend && trend.length > 1 && <Spark points={trend} label={trendLabel ?? label} />}
    </dl>
  )
  return href ? <a className="fb-stat-link" href={href}>{card}</a> : card
}

function Spark({ points, label }: { points: number[]; label: string }) {
  const W = 120, H = 28
  const lo = Math.min(...points), hi = Math.max(...points)
  const y = (v: number) => H - 2 - ((v - lo) / (hi - lo || 1)) * (H - 4)
  const line = points.map((v, i) => `${((i / (points.length - 1)) * W).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg className="fb-stat-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <polyline points={line} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
