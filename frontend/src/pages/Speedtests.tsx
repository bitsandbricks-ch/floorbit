import { Alert, Anchor, Badge, Group, Loader, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { SpeedSeat, SpeedtestSummary } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { StatCard } from '@/components/StatCard'

function SeatList({ seats }: { seats: SpeedSeat[] }) {
  const { t, i18n } = useTranslation()
  const mbps = (n: number | null) => n == null ? '–' : t('speedtests.mbps', { n: n.toLocaleString(i18n.language) })
  return (
    <Text size="sm" style={{ overflowWrap: 'anywhere' }}>
      {seats.map((s, n) => (
        <span key={s.seat}>{n > 0 && ' · '}
          <Anchor underline="always" href={`/plan?seat=${encodeURIComponent(s.seat)}`}>{s.seat}</Anchor> {mbps(s.down_mbps)}
        </span>
      ))}
    </Text>
  )
}

/** The seats' speed tests side by side per switch (issue #434): one slow switch shows up as one row. */
export default function Speedtests() {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const query = useQuery({
    queryKey: qk.speedtests,
    queryFn: () => get<SpeedtestSummary>('/api/speedtests/summary'),
    refetchInterval: 60_000,
  })
  // A new result comes in as an incident change with action "speedtest".
  useLiveEvent('incident.changed', () => { void client.invalidateQueries({ queryKey: qk.speedtests }) })
  const d = query.data
  const num = (n: number | null) => n == null ? '–' : n.toLocaleString(i18n.language)
  const mbps = (n: number | null) => n == null ? '–' : t('speedtests.mbps', { n: num(n) })
  const ms = (n: number | null) => n == null ? '–' : t('speedtests.ms', { n: num(n) })

  return (
    <Layout title={t('speedtests.title')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <PageHead title={t('speedtests.title')} desc={t('speedtests.intro')} />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {query.isPending || !d ? <Loader aria-label={t('common.loading')} /> : d.hall.tests === 0 ? (
          <Alert color="gray" variant="light">{t('speedtests.none', { hours: d.hours })}</Alert>
        ) : (
          <>
            <div className="fb-stat-row">
              <StatCard label={t('speedtests.tests')} value={num(d.hall.tests)} sub={t('speedtests.since', { hours: d.hours })} />
              <StatCard label={t('speedtests.down')} value={mbps(d.hall.down_mbps)} />
              <StatCard label={t('speedtests.up')} value={mbps(d.hall.up_mbps)} />
              <StatCard label={t('speedtests.ping')} value={ms(d.hall.ping_ms)} />
            </div>
            <Paper withBorder radius="lg" p="md">
              {d.switches.length === 0 ? <Text size="sm" c="dimmed">{t('speedtests.noSwitches')}</Text> : (
                <Table.ScrollContainer minWidth={640}>
                  <Table verticalSpacing="xs">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('speedtests.switch')}</Table.Th>
                        <Table.Th ta="right">{t('speedtests.tests')}</Table.Th>
                        <Table.Th ta="right">{t('speedtests.down')}</Table.Th>
                        <Table.Th ta="right">{t('speedtests.up')}</Table.Th>
                        <Table.Th ta="right">{t('speedtests.ping')}</Table.Th>
                        <Table.Th>{t('speedtests.seats')}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {d.switches.map((s) => (
                        <Table.Tr key={s.id}>
                          <Table.Td>
                            <Group gap="xs" wrap="wrap">
                              <Anchor fw={600} href={`/plan?switch=${encodeURIComponent(s.name)}`} style={{ whiteSpace: 'nowrap' }}>{s.name}</Anchor>
                              {s.slow && <Badge size="sm" color="warn" variant="light" title={t('speedtests.slowHint')} style={{ flexShrink: 0 }}>{t('speedtests.slow')}</Badge>}
                            </Group>
                          </Table.Td>
                          <Table.Td ta="right">{num(s.tests)}</Table.Td>
                          <Table.Td ta="right" fw={s.slow ? 700 : undefined} style={{ whiteSpace: 'nowrap' }}>{mbps(s.down_mbps)}</Table.Td>
                          <Table.Td ta="right" style={{ whiteSpace: 'nowrap' }}>{mbps(s.up_mbps)}</Table.Td>
                          <Table.Td ta="right" style={{ whiteSpace: 'nowrap' }}>{ms(s.ping_ms)}</Table.Td>
                          <Table.Td><SeatList seats={s.seats} /></Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
              {d.switches.some((s) => s.slow) && <Text size="xs" c="dimmed" mt="xs">{t('speedtests.slowHint')}</Text>}
            </Paper>
            {d.unknown.length > 0 && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('speedtests.unknown')}</Title>
                <SeatList seats={d.unknown} />
              </Paper>
            )}
          </>
        )}
      </Stack>
    </Layout>
  )
}
