import { Group, SegmentedControl, Table, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { CompareData, ComparePoint, CompareSide } from '@/api/types'
import { bytes } from '../traffic/format'
import { bps } from './format'

const W = 1000
const H = 120

type Row = { key: keyof CompareSide; format: (v: number) => string; higherIsWorse?: boolean }
const ROWS: Row[] = [
  { key: 'peak_bps', format: bps },
  { key: 'avg_bps', format: bps },
  { key: 'bytes_moved', format: bytes },
  { key: 'online_max', format: String },
  { key: 'incidents', format: String, higherIsWorse: true },
  { key: 'outages', format: String, higherIsWorse: true },
]

function change(now: number | null, then: number | null) {
  if (now == null || then == null || then === 0) return null
  return Math.round(((now - then) / then) * 100)
}

/** "+12 %", or for a count that was zero the difference itself ("+3"); past 1000 % only "more than". */
function changeText(now: number | null, then: number | null, c: number | null) {
  if (c == null) return now != null && then === 0 && now > 0 ? `+${now}` : '–'
  if (c > 999) return '> +999 %'
  return `${c > 0 ? '+' : ''}${c} %`
}

/** Average bandwidth per hour: now as a line, then dashed. */
function Lines({ series, label }: { series: ComparePoint[]; label: string }) {
  const top = Math.max(1, ...series.flatMap((p) => [p.now_avg_bps ?? 0, p.then_avg_bps ?? 0]))
  const x = (i: number) => (i / Math.max(1, series.length - 1)) * W
  const y = (v: number) => H - (v / top) * (H - 6)
  const line = (pick: (p: ComparePoint) => number | null) =>
    series.map((p, i) => [i, pick(p)] as const).filter(([, v]) => v != null).map(([i, v]) => `${x(i).toFixed(1)},${y(v as number).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-dns-chart fb-compare-chart" role="img" aria-label={label}>
      {[0.25, 0.5, 0.75].map((f) => <line key={f} className="grid" x1={0} x2={W} y1={H * f} y2={H * f} />)}
      <polyline className="then" points={line((p) => p.then_avg_bps)} />
      <polyline className="now" points={line((p) => p.now_avg_bps)} />
    </svg>
  )
}

/** Today against yesterday, and this event against the last one, each cut to the same length (issue #90). */
export function Compare({ only }: { only?: 'event' }) {
  const { t } = useTranslation()
  const query = useQuery({ queryKey: qk.compare, queryFn: () => get<CompareData>('/api/stats/compare'), refetchInterval: 300_000 })
  const data = query.data
  const [view, setView] = useState<'day' | 'event'>(only ?? 'day')
  if (!data) return null
  const ev = data.event
  if (only === 'event' && !ev) return null
  const which = view === 'event' && ev ? 'event' : 'day'
  const pick = which === 'event' && ev ? ev : data.day
  const thenLabel = which === 'event' && ev ? ev.name : t('stats.compare.yesterday')
  const nowLabel = which === 'event' ? t('stats.compare.thisEvent') : t('stats.compare.today')
  const hours = Math.round((ev?.elapsed_s ?? 0) / 3600)
  return (
    <section className="fb-stats-panel wide" aria-labelledby="stats-compare">
      <Group justify="space-between" mb={6}>
        <h2 id="stats-compare">{t('stats.compare.title')}</h2>
        {!only && ev && (
          <SegmentedControl size="xs" value={which} onChange={(v) => setView(v as 'day' | 'event')} aria-label={t('stats.compare.title')}
            data={[{ value: 'day', label: t('stats.compare.dayView') }, { value: 'event', label: t('stats.compare.eventView', { name: ev.name }) }]} />
        )}
      </Group>
      <Text size="sm" c="dimmed" mb="xs">
        {which === 'event' ? t('stats.compare.eventFair', { count: hours, name: ev?.name }) : t('stats.compare.dayFair')}
      </Text>
      {which === 'day' && !data.day.has_then ? <Text size="sm" c="dimmed">{t('stats.compare.noYesterday')}</Text> : (
        <>
          <Table.ScrollContainer minWidth={480}>
            <Table withRowBorders={false} verticalSpacing={4}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th />
                  <Table.Th>{nowLabel}</Table.Th>
                  <Table.Th>{thenLabel}</Table.Th>
                  <Table.Th>{t('stats.compare.change')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {ROWS.map((r) => {
                  const now = pick.now[r.key] as number | null
                  const then = pick.then[r.key] as number | null
                  const c = change(now, then)
                  const bad = !!r.higherIsWorse && (c != null ? c > 0 : then === 0 && (now ?? 0) > 0)
                  return (
                    <Table.Tr key={r.key}>
                      <Table.Td>{t(`stats.compare.row.${r.key}`)}</Table.Td>
                      <Table.Td fw={600}>{now == null ? '–' : r.format(now)}</Table.Td>
                      <Table.Td>{then == null ? '–' : r.format(then)}</Table.Td>
                      <Table.Td c={bad ? 'down' : 'dimmed'}>{changeText(now, then, c)}</Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group gap="sm" mt="sm" mb={4}>
            <Text size="xs" c="dimmed"><span className="fb-compare-key now" /> {nowLabel}</Text>
            <Text size="xs" c="dimmed"><span className="fb-compare-key then" /> {thenLabel}</Text>
          </Group>
          <Lines series={pick.series} label={t('stats.compare.chartLabel', { now: nowLabel, then: thenLabel })} />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">{which === 'event' ? t('stats.compare.hourN', { n: 1 }) : '00:00'}</Text>
            <Text size="xs" c="dimmed">{which === 'event' ? t('stats.compare.hourN', { n: pick.series.length }) : '24:00'}</Text>
          </Group>
        </>
      )}
    </section>
  )
}
