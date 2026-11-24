import { Alert, Anchor, Button, Group, Paper, SimpleGrid, Stack, Switch, Text, Title } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useFeature } from '@/api/queries'
import type { EventReport, ReportHour } from '@/api/types'
import { ConfirmButton, DataTable, type DataTableProps, ErrorBanner, LoadingState, PageHead, StatTile } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { bytes, duration, hourPath, pdfUrl, stamp } from './report/format'
import { Compare } from './stats/Compare'
import { bps } from './stats/format'
import { incidentTitle } from '@/lib/incidentTitle'

type PortRow = EventReport['problem_ports'][number]
type IncidentRow = EventReport['incidents']['items'][number]

const W = 1000
const H = 140


function Chart({ title, label, hours, children, keys }: {
  title: string; label: string; hours: ReportHour[]; children: (top: number) => ReactNode; keys: { cls: string; text: string }[]
}) {
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb={6}>
        <Text size="sm" fw={600}>{title}</Text>
        <Group gap="sm">
          {keys.map((k) => <Text key={k.cls} size="xs" c="dimmed"><span className={`fb-report-key ${k.cls}`} /> {k.text}</Text>)}
        </Group>
      </Group>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-report-chart" role="img" aria-label={label}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} className="grid" x1={0} x2={W} y1={H * f} y2={H * f} />)}
        {children(Math.max(1, ...hours.flatMap((h) => [h.online_max, h.checked_in])))}
      </svg>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">{stamp(hours[0].t)}</Text>
        <Text size="xs" c="dimmed">{stamp(hours[hours.length - 1].t + 3600)}</Text>
      </Group>
    </Paper>
  )
}

function Section<T>({ title, empty, ...table }: { title: string; empty: string } & Pick<DataTableProps<T>, 'rows' | 'columns' | 'rowKey'>) {
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{title}</Title>
      <DataTable {...table} label={title} urlState={false} pageSize={0} bare striped minWidth={560}
        empty={<Text size="sm" c="dimmed">{empty}</Text>} />
    </Paper>
  )
}

export default function Report() {
  const { t, i18n } = useTranslation()
  const pastEventsOn = useFeature('past_events')
  const qc = useQueryClient()
  const canReset = useCan('settings.manage')
  const [people, setPeople] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const query = useQuery({ queryKey: qk.report(people), queryFn: () => get<EventReport>(`/api/report${people ? '?people=1' : ''}`) })
  const reset = useMutation({
    mutationFn: () => post('/api/report/new-event'),
    onSuccess: () => {
      setNotice(t('report.newEventDone'))
      void qc.invalidateQueries({ queryKey: qk.reports })
    },
  })
  const r = query.data
  const error = query.error ?? reset.error
  const seatsSub = r?.seats ? t('report.ofSeats', { count: r.seats }) : undefined

  return (
    <Layout title={t('report.title')} back={{ href: '/stats', label: t('stats.title') }}>
      <PageHead title={r?.event_name || t('report.title')} desc={t('report.intro')}
        actions={
          <Group gap="xs">
            <Button component="a" leftSection={<IconDownload size={16} />}
              href={pdfUrl(i18n.language, people, new Date().getTimezoneOffset())}>
              {t('report.download')}
            </Button>
            {pastEventsOn && (
              <Button variant="default" component="a" href="/events">{t('report.pastEvents')}</Button>
            )}
            {canReset && (
              <ConfirmButton variant="default" danger label={t('report.newEvent')} question={t('report.newEventQuestion')}
                onConfirm={() => reset.mutate()} loading={reset.isPending} />
            )}
          </Group>
        } />
      <Stack gap="md">
        {notice && <Alert color="up" role="status" withCloseButton onClose={() => setNotice(null)}>{notice}</Alert>}
        <ErrorBanner error={error} />
        {r?.may_add_people && (
          <Switch checked={people} onChange={(e) => setPeople(e.currentTarget.checked)} label={t('report.people')}
            description={t('report.peopleHelp')} />
        )}
        {r?.people && <Alert color="warn" role="note">{t('report.peopleOn')}</Alert>}
        {query.isPending ? <LoadingState rows={3} /> : r && (
          <>
            {r.start && r.end && <Text size="sm" c="dimmed">{t('report.period', { start: stamp(r.start), end: stamp(r.end) })}</Text>}
            <SimpleGrid cols={{ base: 2, sm: 3 }}>
              <StatTile label={t('report.peak')} value={r.peak ? bps(r.peak.bps) : '–'} sub={r.peak ? stamp(r.peak.at) : undefined} />
              <StatTile label={t('report.online')} value={String(r.online_max)} sub={seatsSub} />
              <StatTile label={t('report.checkedIn')} value={String(r.checked_in_max)} sub={seatsSub} />
              <StatTile label={t('report.moved')} value={r.hours.length ? bytes(r.bytes_moved) : '–'} sub={t('report.movedHelp')} />
              <StatTile label={t('report.incidents')} value={String(r.incidents.total)}
                sub={t('report.incidentsSub', { fixed: r.incidents.fixed, open: r.incidents.open })
                  + (r.incidents.median_fix_s ? ` · ${t('report.median', { d: duration(r.incidents.median_fix_s) })}` : '')
                  + (r.incidents.median_take_s ? ` · ${t('report.medianTaken', { d: duration(r.incidents.median_take_s) })}` : '')} />
              <StatTile label={t('report.outages')} value={String(r.outages.reduce((n, o) => n + o.times, 0))}
                sub={t('report.outagesSub', { count: r.outages.length })} />
            </SimpleGrid>

            {pastEventsOn && <div className="fb-stats"><Compare only="event" /></div>}

            {r.hours.length < 2 ? (
              <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('report.empty')}</Text></Paper>
            ) : (
              <SimpleGrid cols={{ base: 1, md: 2 }}>
                <Chart title={t('report.chartSeats')} label={t('report.chartSeatsLabel')} hours={r.hours}
                  keys={[{ cls: 'online', text: t('report.legendOnline') }, { cls: 'checked', text: t('report.legendCheckedIn') }]}>
                  {(top) => (
                    <>
                      <path className="online" d={hourPath(r.hours, 'online_max', top, W, H)} />
                      <path className="checked" d={hourPath(r.hours, 'checked_in', top, W, H)} />
                    </>
                  )}
                </Chart>
                <Chart title={t('report.chartBandwidth')} label={t('report.chartBandwidthLabel')} hours={r.hours}
                  keys={[{ cls: 'bar', text: t('report.legendPeak') }, { cls: 'avg', text: t('report.legendAvg') }]}>
                  {() => {
                    const top = Math.max(1, ...r.hours.map((h) => h.peak_bps))
                    const start = r.hours[0].t
                    const span = r.hours[r.hours.length - 1].t + 3600 - start
                    const bw = (W * 3600) / span
                    return (
                      <>
                        {r.hours.map((h) => (
                          <rect key={h.t} className="bar" x={((h.t - start) / span) * W + bw * 0.15} width={bw * 0.7}
                            y={H - (h.peak_bps / top) * H} height={(h.peak_bps / top) * H} />
                        ))}
                        <path className="avg" d={hourPath(r.hours, 'avg_bps', top, W, H)} />
                      </>
                    )
                  }}
                </Chart>
                {r.hours.some((h) => h.incidents) && (
                  <Chart title={t('report.chartIncidents')} label={t('report.chartIncidentsLabel')} hours={r.hours}
                    keys={[{ cls: 'incidents', text: t('report.legendIncidents') }]}>
                    {() => {
                      const top = Math.max(1, ...r.hours.map((h) => h.incidents ?? 0))
                      const start = r.hours[0].t
                      const span = r.hours[r.hours.length - 1].t + 3600 - start
                      const bw = (W * 3600) / span
                      return r.hours.map((h) => (
                        <rect key={h.t} className="incidents" x={((h.t - start) / span) * W + bw * 0.15} width={bw * 0.7}
                          y={H - ((h.incidents ?? 0) / top) * H} height={((h.incidents ?? 0) / top) * H}>
                          <title>{`${stamp(h.t)}: ${h.incidents ?? 0}`}</title>
                        </rect>
                      ))
                    }}
                  </Chart>
                )}
              </SimpleGrid>
            )}

            <Section title={t('report.outages')} empty={t('report.noOutages')} rows={r.outages} rowKey={(o) => o.switch}
              columns={[
                { id: 'switch', header: t('report.switch'), sort: (o) => o.switch, cell: (o) => o.switch },
                { id: 'times', header: t('report.times'), numeric: true, descFirst: true, sort: (o) => o.times, cell: (o) => o.times },
                { id: 'down', header: t('report.downAll'), descFirst: true, sort: (o) => o.down_s,
                  cell: (o) => <>{duration(o.down_s)}{o.still_down && <Text span c="down" size="sm"> · {t('report.stillDown')}</Text>}</> },
                { id: 'longest', header: t('report.longest'), descFirst: true, sort: (o) => o.longest_s, cell: (o) => duration(o.longest_s) },
              ]} />

            <Section title={t('report.ports')} empty={t('report.noPorts')} rows={r.problem_ports} rowKey={(p) => `${p.switch}|${p.port}`}
              columns={[
                { id: 'switch', header: t('report.switch'), sort: (p) => p.switch, cell: (p) => p.switch },
                { id: 'port', header: t('report.port'), sort: (p) => p.port, cell: (p) => p.port },
                { id: 'seat', header: t('report.seat'), sort: (p) => p.seat, cell: (p) => p.seat ?? '–' },
                { id: 'count', header: t('report.problems'), numeric: true, descFirst: true, sort: (p) => p.count, cell: (p) => p.count },
                { id: 'what', header: t('report.what'), wrap: true,
                  cell: (p) => Object.entries(p.kinds).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${t(`report.kind_${k}`, { defaultValue: k })} ${n}×`).join(', ') },
                ...(r.people ? [
                  { id: 'nick', header: t('report.nick'), cell: (p: PortRow) => p.nick ?? '–' },
                  { id: 'ip', header: t('report.ip'), mono: true, cell: (p: PortRow) => p.ip ?? '–' },
                ] : []),
              ]} />

            <Section title={t('report.incidents')} empty={t('report.noIncidents')} rows={r.incidents.items} rowKey={(i, n) => `${i.start}-${n}`}
              columns={[
                { id: 'opened', header: t('report.opened'), sort: (i) => i.start, cell: (i) => stamp(i.start) },
                { id: 'where', header: t('report.where'), sort: (i) => i.seat ?? i.switch ?? i.circuit, cell: (i) => i.seat ?? i.switch ?? i.circuit ?? '–' },
                { id: 'what', header: t('report.what'), wrap: true, cell: (i) => (
                  <>{incidentTitle(i.title, t)}{i.source === 'helpdesk' && <Text span c="dimmed" size="xs"> ({t('report.fromSeat')}{i.reports > 1 ? `, ${i.reports}×` : ''})</Text>}</>
                ) },
                { id: 'team', header: t('report.team'), sort: (i) => i.team, cell: (i) => i.team ?? '–' },
                { id: 'took', header: t('report.took'), descFirst: true, sort: (i) => (i.end ? i.end - i.start : Number.MAX_SAFE_INTEGER),
                  cell: (i) => (i.end ? duration(i.end - i.start) : <Text span c="down" size="sm">{t('report.open')}</Text>) },
                ...(r.people ? [
                  { id: 'reporter', header: t('report.reportedBy'), cell: (i: IncidentRow) => i.reported_by ?? '–' },
                  { id: 'nick', header: t('report.nick'), cell: (i: IncidentRow) => i.nick ?? '–' },
                ] : []),
              ]} />
            {/* Underlined: in the dark theme the link colour alone is too close to the text around it (issue #356). */}
            {!!r.incidents.repeat_seats?.length && (
              <Text size="sm">
                {t('report.repeatSeats')}{' '}
                {r.incidents.repeat_seats.map((x, n) => (
                  <span key={x.seat}>{n > 0 && ', '}<Anchor underline="always" href={`/plan?seat=${encodeURIComponent(x.seat)}`}>{x.seat}</Anchor> ({x.count}×)</span>
                ))}
              </Text>
            )}
            {!!r.incidents.seat_problems?.length && (
              <Text size="sm">
                {t('report.seatProblems', {
                  what: r.incidents.seat_problems.map((x) => `${t(`report.problem_${x.problem}`, { defaultValue: x.problem })} ${x.count}×`).join(', '),
                })}
              </Text>
            )}
            {r.incidents.total > r.incidents.items.length && (
              <Text size="xs" c="dimmed">{t('report.cut', { count: r.incidents.items.length, total: r.incidents.total })}</Text>
            )}
            <Text size="xs" c="dimmed">{t('report.kept')}</Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
