import { Button, Group, SegmentedControl, Text } from '@mantine/core'
import { IconFileText, IconPlayerPlay } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useFeature, useStats } from '@/api/queries'
import type { StatsData, StatsSample } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import type { ViewProps } from '@/widgets/views'
import { StatCard } from '@/components/StatCard'
import { Compare } from './Compare'
import { Forecast } from './Forecast'
import { bps } from './format'
import { onPlan } from '../plan/links'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { clock } from '@/lib/time'

const HOUR = 3600


/** Traffic over time: download as an area, upload as a line, with the busiest point marked. */
function Chart({ series, label }: { series: StatsSample[]; label: string }) {
  const { t } = useTranslation()
  if (series.length < 2) return <Text c="dimmed" size="sm">{t('stats.collecting')}</Text>
  const W = 600, H = 160
  const t0 = series[0].t, t1 = series[series.length - 1].t
  const top = Math.max(...series.map((s) => s.down + s.up), 1)
  const x = (ts: number) => ((ts - t0) / (t1 - t0 || 1)) * W
  const y = (v: number) => H - (v / top) * (H - 8)
  const total = series.map((s) => `${x(s.t).toFixed(1)},${y(s.down + s.up).toFixed(1)}`).join(' ')
  const up = series.map((s) => `${x(s.t).toFixed(1)},${y(s.up).toFixed(1)}`).join(' ')
  return (
    <figure className="fb-stats-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <polygon className="total" points={`0,${H} ${total} ${W},${H}`} />
        <polyline className="total-line" points={total} vectorEffect="non-scaling-stroke" />
        <polyline className="up" points={up} vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption>
        <span>{clock(t0)}</span>
        <span className="legend"><i className="total" /> {t('stats.total')} <i className="up" /> {t('stats.upload')} · {t('stats.max', { value: bps(top) })}</span>
        <span>{clock(t1)}</span>
      </figcaption>
    </figure>
  )
}

// A wall screen has nobody to scroll it: the busiest rows only, so the page fits a TV.
const SCREEN_ROWS = 8

function Board({ data, screen }: { data: StatsData; screen: boolean }) {
  const rows = screen ? SCREEN_ROWS : Infinity
  const { t } = useTranslation()
  const forecastOn = useFeature('forecast')
  const [range, setRange] = useState<'hour' | 'day'>(screen ? 'hour' : 'day')
  const now = data.now
  const since = (data.last_poll ?? data.series.at(-1)?.t ?? 0) - (range === 'hour' ? HOUR : 24 * HOUR)
  const series = data.series.filter((s) => s.t >= since)
  const lastHour = data.series.filter((s) => s.t >= (data.last_poll ?? data.series.at(-1)?.t ?? 0) - HOUR)
  if (!now) {
    return <Text c="dimmed">{data.monitoring ? t('stats.collecting') : t('stats.noMonitoring')}</Text>
  }
  return (
    <div className="fb-stats">
      <div className="fb-stats-row" role="group" aria-label={t('stats.bandwidth')}>
        <StatCard label={t('stats.now')} value={bps(now.down + now.up)} trend={lastHour.map((s) => s.down + s.up)}
          trendLabel={t('stats.trendTraffic')} sub={t('stats.downUp', { down: bps(now.down), up: bps(now.up) })} />
        {data.hour && <StatCard label={t('stats.hour')} value={bps(data.hour.peak_bps)} sub={t('stats.avg', { value: bps(data.hour.avg_bps) })} />}
        {data.day && <StatCard label={t('stats.day')} value={bps(data.day.peak_bps)} sub={t('stats.avg', { value: bps(data.day.avg_bps) })} />}
        {data.peak && <StatCard label={t('stats.peak')} value={bps(data.peak.bps)} sub={t('stats.at', { time: clock(data.peak.at) })} />}
        <StatCard label={t('stats.online')} value={String(now.online)} trend={lastHour.map((s) => s.online)} trendLabel={t('stats.trendOnline')}
          sub={data.day ? t('stats.onlineMax', { count: data.day.online_max }) : undefined} />
        <StatCard label={t('stats.ports')} value={t('stats.portsUp', { count: now.ports_up })}
          tone={now.ports_errors ? 'warn' : undefined} href={screen ? undefined : '/problems'}
          sub={t('stats.portsRest', { down: now.ports_down, errors: now.ports_errors })} />
      </div>

      <section className="fb-stats-panel wide" aria-labelledby="stats-traffic">
        <Group justify="space-between" mb={6}>
          <h2 id="stats-traffic">{t('stats.traffic')}</h2>
          <SegmentedControl size="xs" value={range} onChange={(v) => setRange(v as 'hour' | 'day')}
            data={[{ value: 'hour', label: t('stats.lastHour') }, { value: 'day', label: t('stats.lastDay') }]} />
        </Group>
        <Chart series={series} label={t('stats.chartLabel')} />
        <OnlineLine series={series} />
      </section>

      {forecastOn && !screen && <Forecast />}
      {!screen && <Compare />}

      <section className="fb-stats-panel" aria-labelledby="stats-uplinks">
        <h2 id="stats-uplinks">{t('stats.uplinks')}</h2>
        {!data.uplinks.length ? <Text c="dimmed" size="sm">{t('stats.noUplinks')}</Text> : (
          <ul className="fb-stats-bars">
            {data.uplinks.slice(0, rows).map((u) => {
              const pct = Math.round((u.utilization ?? 0) * 100)
              return (
                <li key={u.switch_id} className={pct >= 80 ? 'down' : pct >= 60 ? 'warn' : ''}>
                  <span className="name">{screen ? u.switch : <a href={onPlan({ switch: u.switch })}>{u.switch}</a>} <small>{u.port}</small></span>
                  <span className="bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
                    aria-label={`${u.switch} ${u.port}`}><i style={{ width: `${Math.min(100, pct)}%` }} /></span>
                  <span className="value">{pct} % · {bps(u.bps)}</span>
                </li>
              )
            })}
          </ul>
        )}
        {data.uplinks.length > rows && <Text c="dimmed" size="sm" mt={6}>{t('stats.moreUplinks', { count: data.uplinks.length - rows })}</Text>}
      </section>

      <section className="fb-stats-panel" aria-labelledby="stats-top">
        <h2 id="stats-top">{t('stats.top')}</h2>
        {!data.top.length ? <Text c="dimmed" size="sm">{t('stats.noTop')}</Text> : (
          <ol className="fb-stats-top">
            {data.top.slice(0, rows).map((r) => (
              <li key={`${r.switch_id}:${r.port}`}>
                <span className="name">
                  {screen ? (r.seat ? t('stats.seat', { seat: r.seat }) : `${r.switch} ${r.port}`) : (
                    <a href={onPlan({ seat: r.seat, switch: r.switch })}>
                      {r.seat ? t('stats.seat', { seat: r.seat }) : `${r.switch} ${r.port}`}
                    </a>
                  )}
                  {r.nick && <small> · {r.nick}</small>}
                </span>
                <span className="value">{bps(r.bps)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}

function OnlineLine({ series }: { series: StatsSample[] }) {
  const { t } = useTranslation()
  if (series.length < 2) return null
  const lo = Math.min(...series.map((s) => s.online))
  const hi = Math.max(...series.map((s) => s.online))
  return (
    <Text size="sm" c="dimmed" mt={6}>{t('stats.onlineRange', { lo, hi })}</Text>
  )
}

/** Bandwidth now, the hour, the day and the event's peak, uplinks and top talkers (issue #24).
 *  Small, the busiest rows only and no nicks, for a wall; opened up, everything with the peak reset. */
export default function StatsView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const replayOn = useFeature('replay')
  const reportOn = useFeature('report')
  const client = useQueryClient()
  const stats = useStats(!expanded)
  const canReset = useCan('settings.manage')
  useLiveEvent('stats.changed', () => void client.invalidateQueries({ queryKey: qk.statsAll }))
  const reset = useMutation({
    mutationFn: () => post('/api/stats/peak/reset'),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.statsAll }),
  })
  const error = stats.error ?? reset.error
  const updated = stats.data?.last_poll ? t('stats.updated', { time: clock(stats.data.last_poll) }) : null
  return (
    <>
      {expanded && (
        <Group justify="space-between" mb="sm" wrap="wrap">
          <Text size="sm" c="dimmed">{updated}</Text>
          <Group gap="xs">
            {replayOn && (
              <Button variant="default" component="a" href="/replay" leftSection={<IconPlayerPlay size={16} />}>
                {t('stats.replay')}
              </Button>
            )}
            {reportOn && (
              <Button variant="default" component="a" href="/report" leftSection={<IconFileText size={16} />}>
                {t('stats.report')}
              </Button>
            )}
            {canReset && stats.data?.peak && (
              <ConfirmButton variant="default" danger label={t('stats.resetPeak')} question={t('stats.resetConfirm')}
                onConfirm={() => reset.mutate()} loading={reset.isPending} />
            )}
          </Group>
        </Group>
      )}
      <ErrorBanner error={error} mb="md" />
      {stats.isPending ? <LoadingState lines={!expanded} /> : stats.data && <Board data={stats.data} screen={!expanded} />}
    </>
  )
}
