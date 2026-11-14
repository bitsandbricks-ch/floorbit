import { Alert, Anchor, Badge, Button, Group, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { IconExternalLink, IconMapPin } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PlanSeat, SeatDetails, SeatState } from '@/api/types'
import { SeatActions } from './Actions'
import { SeatNoteBox } from './SeatNoteBox'
import { WatchSeat } from './WatchSeat'
import { HEAT_GRADIENT, HEAT_MAX, HEAT_MIN, linkSpans, rate } from './model'
import { SeatGlyph } from './SeatMap'

const TONE: Record<SeatState, string> = { online: 'up', offline: 'down', unknown: 'gray' }

/** Everything about one seat in one place: state, port, check-in, match, incidents and, with
 *  seats.view, who sits there. */
export function Inspector({ seat, onClose, onBlock }: { seat: string; onClose: () => void; onBlock?: (block: string) => void }) {
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
              {row(t('plan.block'), d.block && onBlock
                ? <Anchor component="button" type="button" onClick={() => onBlock(d.block)} aria-label={t('plan.blockPanel.open', { name: d.block })}>{d.block}</Anchor>
                : d.block || '–')}
              {row(t('plan.port'), d.switch ? `${d.switch} · ${d.port}` : <Text span c="dimmed">{t('plan.noPort')}</Text>)}
              {d.bps !== null && row(t('plan.traffic'), rate(d.bps))}
              {d.checked_in !== null && row(t('plan.checkin'), d.checked_in ? t('plan.yes') : t('plan.no'))}
              {d.people && row(t('plan.nick'), d.nick || '–')}
              {d.people && row(t('plan.ip'), d.ip ? <code>{d.ip}</code> : '–')}
              {d.people && row(t('plan.mac'), d.mac ? <code>{d.mac}</code> : '–')}
            </Table.Tbody>
          </Table>
          {d.history && d.switch && <LinkHistory history={d.history} />}
          {!d.people && <Text size="sm" c="dimmed">{t('plan.noPeople')}</Text>}
          {d.crew && <SeatNoteBox key={seat} seat={seat} note={d.note} />}
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
            {d.switch && <WatchSeat seat={seat} />}
            <Button component="a" href={`/?seat=${encodeURIComponent(seat)}`} variant="default" size="xs" leftSection={<IconMapPin size={14} />}>{t('plan.openEditor')}</Button>
            <Button component="a" href="/incidents" variant="default" size="xs" leftSection={<IconExternalLink size={14} />}>{t('plan.incidents')}</Button>
          </Group>
        </>
      )}
    </Stack>
  )
}

/** The seat's link over the last hours (issue #167). Offline is a thin red bar under the line and
 *  online a full green one, so the two differ by shape too; not known yet is left empty. */
function LinkHistory({ history }: { history: NonNullable<SeatDetails['history']> }) {
  const { t, i18n } = useTranslation()
  const spans = linkSpans(history)
  const span = Math.max(1, history.to - history.from)
  const x = (ts: number) => ((ts - history.from) / span) * 1000
  const time = (ts: number) => new Date(ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
  const last = spans[spans.length - 1]
  const hours = Math.round(span / 3600)
  const changes = history.changes.filter(([ts]) => ts > history.from).length
  const since = last && last.on !== null && last.from > history.from
    ? t(last.on ? 'plan.history.onlineSince' : 'plan.history.offlineSince', { time: time(last.from) })
    : last && last.on !== null ? t(last.on ? 'plan.history.onlineAll' : 'plan.history.offlineAll', { count: hours }) : null
  return (
    <Stack gap={4}>
      <Title order={3} size="h5">{t('plan.history.title')}</Title>
      <svg className="fb-link-history" viewBox="0 0 1000 16" preserveAspectRatio="none" role="img"
        aria-label={[since, t('plan.history.changes', { count: changes, hours })].filter(Boolean).join('. ')}>
        <line x1={0} x2={1000} y1={15.5} y2={15.5} className="axis" />
        {spans.filter((s) => s.on !== null).map((s, i) => (
          <rect key={i} className={s.on ? 'on' : 'off'} x={x(s.from)} width={Math.max(4, x(s.to) - x(s.from))} y={s.on ? 0 : 11} height={s.on ? 16 : 5} />
        ))}
      </svg>
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">{t('plan.history.ago', { count: hours })}</Text>
        <Text size="xs" c="dimmed">{t('plan.history.now')}</Text>
      </Group>
      <Text size="sm">{[since, t('plan.history.changes', { count: changes, hours })].filter(Boolean).join(' · ')}</Text>
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
  { key: 'recent', seat: { state: 'offline', changed: 1 } },
  { key: 'note', seat: { state: 'online', note: true } },
]

/** The same shapes as on the plan, so the legend can't drift from it. */
export function Legend({ checkin, traffic = false }: { checkin: boolean; traffic?: boolean }) {
  const { t } = useTranslation()
  return (
    <ul className="fb-plan-legend" aria-label={t('plan.legend')}>
      {traffic && (
        <li className="heat">
          {t('plan.trafficScale')} <span>{rate(HEAT_MIN)}</span><i style={{ background: HEAT_GRADIENT }} aria-hidden="true" /><span>{rate(HEAT_MAX)}</span>
        </li>
      )}
      {SAMPLES.filter((x) => checkin || x.key !== 'checkedIn').map((x) => (
        <li key={x.key}>
          <svg viewBox="-4 -4 40 40" width={22} height={22} aria-hidden="true" className="fb-plan"><SeatGlyph seat={x.seat} size={32} detail /></svg>
          {t(`plan.legendItem.${x.key}`)}
        </li>
      ))}
    </ul>
  )
}
