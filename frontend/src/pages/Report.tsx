import { Alert, Button, Group, Loader, Paper, SimpleGrid, Stack, Switch, Table, Text, Title } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { EventReport, ReportHour } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { bytes, duration, hourPath, pdfUrl, stamp } from './report/format'
import { bps } from './stats/format'

const W = 1000
const H = 140

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper withBorder radius="lg" p="sm">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={700} size="xl">{value}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </Paper>
  )
}

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

function Section({ title, empty, rows, head }: { title: string; empty: string; rows: ReactNode[]; head: string[] }) {
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{title}</Title>
      {rows.length === 0 ? <Text size="sm" c="dimmed">{empty}</Text> : (
        <Table.ScrollContainer minWidth={560}>
          <Table striped>
            <Table.Thead><Table.Tr>{head.map((h) => <Table.Th key={h}>{h}</Table.Th>)}</Table.Tr></Table.Thead>
            <Table.Tbody>{rows}</Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Paper>
  )
}

export default function Report() {
  const { t, i18n } = useTranslation()
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
            <Button variant="default" component="a" href="/events">{t('report.pastEvents')}</Button>
            {canReset && (
              <ConfirmButton variant="default" danger label={t('report.newEvent')} question={t('report.newEventQuestion')}
                onConfirm={() => reset.mutate()} loading={reset.isPending} />
            )}
          </Group>
        } />
      <Stack gap="md">
        {notice && <Alert color="up" role="status" withCloseButton onClose={() => setNotice(null)}>{notice}</Alert>}
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {r?.may_add_people && (
          <Switch checked={people} onChange={(e) => setPeople(e.currentTarget.checked)} label={t('report.people')}
            description={t('report.peopleHelp')} />
        )}
        {r?.people && <Alert color="warn" role="note">{t('report.peopleOn')}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : r && (
          <>
            {r.start && r.end && <Text size="sm" c="dimmed">{t('report.period', { start: stamp(r.start), end: stamp(r.end) })}</Text>}
            <SimpleGrid cols={{ base: 2, sm: 3 }}>
              <Figure label={t('report.peak')} value={r.peak ? bps(r.peak.bps) : '–'} sub={r.peak ? stamp(r.peak.at) : undefined} />
              <Figure label={t('report.online')} value={String(r.online_max)} sub={seatsSub} />
              <Figure label={t('report.checkedIn')} value={String(r.checked_in_max)} sub={seatsSub} />
              <Figure label={t('report.moved')} value={r.hours.length ? bytes(r.bytes_moved) : '–'} sub={t('report.movedHelp')} />
              <Figure label={t('report.incidents')} value={String(r.incidents.total)}
                sub={t('report.incidentsSub', { fixed: r.incidents.fixed, open: r.incidents.open })
                  + (r.incidents.median_fix_s ? ` · ${t('report.median', { d: duration(r.incidents.median_fix_s) })}` : '')} />
              <Figure label={t('report.outages')} value={String(r.outages.reduce((n, o) => n + o.times, 0))}
                sub={t('report.outagesSub', { count: r.outages.length })} />
            </SimpleGrid>

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
              </SimpleGrid>
            )}

            <Section title={t('report.outages')} empty={t('report.noOutages')}
              head={[t('report.switch'), t('report.times'), t('report.downAll'), t('report.longest')]}
              rows={r.outages.map((o) => (
                <Table.Tr key={o.switch}>
                  <Table.Td>{o.switch}</Table.Td>
                  <Table.Td>{o.times}</Table.Td>
                  <Table.Td>{duration(o.down_s)}{o.still_down && <Text span c="down" size="sm"> · {t('report.stillDown')}</Text>}</Table.Td>
                  <Table.Td>{duration(o.longest_s)}</Table.Td>
                </Table.Tr>
              ))} />

            <Section title={t('report.ports')} empty={t('report.noPorts')}
              head={[t('report.switch'), t('report.port'), t('report.seat'), t('report.problems'), t('report.what'),
                ...(r.people ? [t('report.nick'), t('report.ip')] : [])]}
              rows={r.problem_ports.map((p) => (
                <Table.Tr key={`${p.switch}|${p.port}`}>
                  <Table.Td>{p.switch}</Table.Td>
                  <Table.Td>{p.port}</Table.Td>
                  <Table.Td>{p.seat ?? '–'}</Table.Td>
                  <Table.Td>{p.count}</Table.Td>
                  <Table.Td>{Object.entries(p.kinds).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${t(`report.kind_${k}`, { defaultValue: k })} ${n}×`).join(', ')}</Table.Td>
                  {r.people && <><Table.Td>{p.nick ?? '–'}</Table.Td><Table.Td>{p.ip ?? '–'}</Table.Td></>}
                </Table.Tr>
              ))} />

            <Section title={t('report.incidents')} empty={t('report.noIncidents')}
              head={[t('report.opened'), t('report.where'), t('report.what'), t('report.team'), t('report.took'),
                ...(r.people ? [t('report.reportedBy'), t('report.nick')] : [])]}
              rows={r.incidents.items.map((i, n) => (
                <Table.Tr key={n}>
                  <Table.Td>{stamp(i.start)}</Table.Td>
                  <Table.Td>{i.seat ?? i.switch ?? i.circuit ?? '–'}</Table.Td>
                  <Table.Td>{i.title}{i.source === 'helpdesk' && <Text span c="dimmed" size="xs"> ({t('report.fromSeat')}{i.reports > 1 ? `, ${i.reports}×` : ''})</Text>}</Table.Td>
                  <Table.Td>{i.team ?? '–'}</Table.Td>
                  <Table.Td>{i.end ? duration(i.end - i.start) : <Text span c="down" size="sm">{t('report.open')}</Text>}</Table.Td>
                  {r.people && <><Table.Td>{i.reported_by ?? '–'}</Table.Td><Table.Td>{i.nick ?? '–'}</Table.Td></>}
                </Table.Tr>
              ))} />
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
