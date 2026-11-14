import { Alert, Badge, Button, Group, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { IconExternalLink, IconMapPin } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PlanSeat, SeatDetails, SeatState } from '@/api/types'
import { SeatActions } from './Actions'
import { rate } from './model'
import { SeatGlyph } from './SeatMap'

const TONE: Record<SeatState, string> = { online: 'up', offline: 'down', unknown: 'gray' }

/** Everything about one seat in one place: state, port, check-in, match, incidents and, with
 *  seats.view, who sits there. */
export function Inspector({ seat, onClose }: { seat: string; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const q = useQuery({ queryKey: qk.planSeat(seat), queryFn: () => get<SeatDetails>(`/api/plan/seats/${encodeURIComponent(seat)}`) })
  const d = q.data
  // Like the plan: a missing check-in is listed but not counted as a problem.
  const problems = d ? d.incidents.length + d.attention.filter((a) => a.kind !== 'checkin').length : 0
  const clock = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  const row = (label: string, value: React.ReactNode) => (
    <Table.Tr key={label}><Table.Th scope="row" fw={500} c="dimmed" w="40%">{label}</Table.Th><Table.Td>{value}</Table.Td></Table.Tr>
  )
  return (
    <Stack gap="sm" className="fb-inspector" aria-live="polite">
      <Group justify="space-between" wrap="nowrap">
        <Title order={2} size="h3">{t('plan.seat', { seat })}</Title>
        <Button variant="subtle" size="compact-sm" onClick={onClose}>{t('plan.close')}</Button>
      </Group>
      {q.isPending && <Loader size="sm" aria-label={t('common.loading')} />}
      {q.error && <Alert color="down" role="alert">{t('common.error', { message: q.error.message })}</Alert>}
      {d && (
        <>
          <Group gap="xs">
            <Badge color={TONE[d.state]} variant={d.state === 'online' ? 'filled' : 'outline'}>{t(`plan.state.${d.state}`)}</Badge>
            {d.checked_in && <Badge color="trace" variant="light">{t('plan.checkedIn')}</Badge>}
            {d.match && <Badge color="warn" variant="light">{t('plan.matchIn', { zone: d.match })}</Badge>}
            {problems > 0 && <Badge color="down" variant="light">{t('plan.problemsN', { count: problems })}</Badge>}
          </Group>
          <Table withRowBorders={false} verticalSpacing={4}>
            <Table.Tbody>
              {row(t('plan.block'), d.block || '–')}
              {row(t('plan.port'), d.switch ? `${d.switch} · ${d.port}` : <Text span c="dimmed">{t('plan.noPort')}</Text>)}
              {d.bps !== null && row(t('plan.traffic'), rate(d.bps))}
              {d.checked_in !== null && row(t('plan.checkin'), d.checked_in ? t('plan.yes') : t('plan.no'))}
              {d.people && row(t('plan.nick'), d.nick || '–')}
              {d.people && row(t('plan.ip'), d.ip ? <code>{d.ip}</code> : '–')}
              {d.people && row(t('plan.mac'), d.mac ? <code>{d.mac}</code> : '–')}
            </Table.Tbody>
          </Table>
          {!d.people && <Text size="sm" c="dimmed">{t('plan.noPeople')}</Text>}
          {(d.incidents.length > 0 || d.attention.length > 0) && (
            <Stack gap={4}>
              <Title order={3} size="h5">{t('plan.problems')}</Title>
              {d.incidents.map((i) => (
                <Text key={i.id} size="sm">{i.title} <Text span c="dimmed" size="xs">({t(`plan.incidentStatus.${i.status}`, { defaultValue: i.status })}, {clock(i.created_at)})</Text></Text>
              ))}
              {d.attention.map((a, n) => <Text key={n} size="sm">{a.title} <Text span c="dimmed" size="xs">({t('plan.since', { time: clock(a.since) })})</Text></Text>)}
            </Stack>
          )}
          <SeatActions seat={seat} hasPort={!!d.switch} />
          <Group gap="xs">
            <Button component="a" href={`/?seat=${encodeURIComponent(seat)}`} variant="default" size="xs" leftSection={<IconMapPin size={14} />}>{t('plan.openEditor')}</Button>
            <Button component="a" href="/incidents" variant="default" size="xs" leftSection={<IconExternalLink size={14} />}>{t('plan.incidents')}</Button>
          </Group>
        </>
      )}
    </Stack>
  )
}

const SAMPLES: { key: string; seat: PlanSeat }[] = [
  { key: 'online', seat: { state: 'online' } },
  { key: 'offline', seat: { state: 'offline' } },
  { key: 'unknown', seat: { state: 'unknown' } },
  { key: 'checkedIn', seat: { state: 'online', checked_in: true } },
  { key: 'problem', seat: { state: 'offline', problems: 1 } },
  { key: 'match', seat: { state: 'online', match: 'x' } },
]

/** The same shapes as on the plan, so the legend can't drift from it. */
export function Legend({ checkin }: { checkin: boolean }) {
  const { t } = useTranslation()
  return (
    <ul className="fb-plan-legend" aria-label={t('plan.legend')}>
      {SAMPLES.filter((x) => checkin || x.key !== 'checkedIn').map((x) => (
        <li key={x.key}>
          <svg viewBox="-4 -4 40 40" width={22} height={22} aria-hidden="true" className="fb-plan"><SeatGlyph seat={x.seat} size={32} detail /></svg>
          {t(`plan.legendItem.${x.key}`)}
        </li>
      ))}
    </ul>
  )
}
