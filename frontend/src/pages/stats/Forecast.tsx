import { Alert, Group, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { ForecastData } from '@/api/types'
import { bps } from './format'

const W = 1000
const H = 140

/** The next hours' expected busiest read, with the range from the quietest and busiest day, and the
 *  line's capacity (issue #89). Explains how it was worked out, so nobody has to trust a black box. */
export function Forecast() {
  const { t, i18n } = useTranslation()
  const query = useQuery({ queryKey: qk.forecast, queryFn: () => get<ForecastData>('/api/forecast'), refetchInterval: 300_000 })
  const f = query.data
  if (!f) return null
  const hour = (ts: number) => new Date(ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
  return (
    <section className="fb-stats-panel wide" aria-labelledby="stats-forecast">
      <Group justify="space-between" mb={6}>
        <h2 id="stats-forecast">{t('stats.forecast.title')}</h2>
        {f.ready && (
          <Group gap="sm">
            <Text size="xs" c="dimmed"><span className="fb-dns-key hit" /> {t('stats.forecast.expected')}</Text>
            <Text size="xs" c="dimmed"><span className="fb-dns-key miss" /> {t('stats.forecast.range')}</Text>
            {f.capacity_bps && <Text size="xs" c="dimmed"><span className="fb-dns-key blocked" /> {t('stats.forecast.capacity')}</Text>}
          </Group>
        )}
      </Group>
      {!f.ready ? (
        <Text size="sm" c="dimmed">{t('stats.forecast.notYet', { count: f.min_hours, have: f.history_hours })}</Text>
      ) : (
        <>
          {f.alert && (
            <Alert color={f.alert.pct >= 100 ? 'down' : 'warn'} mb="sm" role="alert">
              {t('stats.forecast.alert', { pct: f.alert.pct, time: hour(f.alert.t), value: bps(f.alert.bps) })}
            </Alert>
          )}
          <ForecastChart f={f} label={t('stats.forecast.chartLabel', { value: bps(f.peak?.bps), time: hour(f.peak?.t ?? 0) })} />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">{hour(f.points[0].t)}</Text>
            <Text size="xs" c="dimmed">{hour(f.points[f.points.length - 1].t + 3600)}</Text>
          </Group>
          <Text size="sm" c="dimmed" mt={6}>
            {t('stats.forecast.how', { count: f.days })}{' '}
            {f.level == null ? t('stats.forecast.noLevel')
              : t('stats.forecast.level', { pct: Math.round(Math.abs(f.level - 1) * 100), dir: t(f.level >= 1 ? 'stats.forecast.busier' : 'stats.forecast.quieter') })}
            {!f.capacity_bps && <> {t('stats.forecast.noCapacity')}</>}
          </Text>
        </>
      )}
    </section>
  )
}

function ForecastChart({ f, label }: { f: ForecastData; label: string }) {
  const top = Math.max(1, ...f.points.map((p) => p.high), f.capacity_bps ?? 0) * 1.05
  const w = W / f.points.length
  const y = (v: number) => H - (v / top) * H
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-dns-chart" role="img" aria-label={label}>
      {[0.25, 0.5, 0.75].map((x) => <line key={x} className="grid" x1={0} x2={W} y1={H * x} y2={H * x} />)}
      {f.points.map((p, i) => (
        <g key={p.t}>
          <rect className="miss" x={i * w + w * 0.15} width={w * 0.7} y={y(p.high)} height={Math.max(1, y(p.low) - y(p.high))} />
          <rect className="hit" x={i * w + w * 0.3} width={w * 0.4} y={y(p.bps)} height={H - y(p.bps)} />
        </g>
      ))}
      {f.capacity_bps && (
        <line className="capacity" x1={0} x2={W} y1={y(f.capacity_bps)} y2={y(f.capacity_bps)} />
      )}
    </svg>
  )
}
