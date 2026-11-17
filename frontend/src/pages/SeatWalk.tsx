import { Alert, Badge, Button, Checkbox, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { IconCircleCheck, IconCircleX, IconPlugConnected } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { SeatBlock, SeatLocated, SeatWalkInfo, WalkPort } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

/** How long the page keeps asking before it says the lookup failed. Each request tries about 20 s;
 *  a monitoring source that only polls the MAC tables every minute or so needs a few of them. */
export const GIVE_UP_MS = 90_000

type Done = { seat: string; port: WalkPort; how: SeatLocated['how']; ms: number }
type Status =
  | { kind: 'idle' }
  | { kind: 'looking'; started: number; last?: SeatLocated }
  | { kind: 'found'; result: SeatLocated; ms: number }
  | { kind: 'failed'; result?: SeatLocated; error?: string }

const portText = (p: WalkPort) => `${p.switch} ${p.port}`

/** The walk: one seat at a time. Plug in, Locate, see the port (or why not), next seat. */
function Walk({ info, seats, startAt, onStop }: {
  info: SeatWalkInfo; seats: { seat: string; port: WalkPort | null }[]; startAt: number; onStop: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canFixPlan = useCan('floorplan.edit')
  const [at, setAt] = useState(startAt)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [done, setDone] = useState<Done[]>([])
  const [now, setNow] = useState(() => Date.now())
  const [planFixed, setPlanFixed] = useState(false)
  const run = useRef(0)                      // a new Locate, Cancel or seat drops answers of the old one
  const laptop = useRef<{ mac: string; ip: string } | null>(null)
  const previous = useRef<WalkPort | null>(null)
  const seat = seats[at]?.seat

  useEffect(() => {
    if (status.kind !== 'looking') return
    const timer = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [status.kind])

  const locate = useCallback(async () => {
    if (!seat) return
    const mine = ++run.current
    const started = Date.now()
    setPlanFixed(false)
    setNow(started)
    setStatus({ kind: 'looking', started })
    for (;;) {
      let result: SeatLocated
      try {
        result = await post<SeatLocated>('/api/seat-walk/locate', {
          seat, previous: previous.current, mac: laptop.current?.mac, mac_ip: laptop.current?.ip })
      } catch (e) {
        if (run.current === mine) setStatus({ kind: 'failed', error: e instanceof ApiError ? e.message : String(e) })
        return
      }
      if (run.current !== mine) return
      if (result.mac) laptop.current = { mac: result.mac, ip: result.ip }
      if (result.ok && result.found) {
        previous.current = result.found
        const row: Done = { seat, port: result.found, how: result.how, ms: Date.now() - started }
        setDone((d) => [row, ...d.filter((x) => x.seat !== seat)])
        setStatus({ kind: 'found', result, ms: row.ms })
        void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
        return
      }
      if (!result.retry || Date.now() - started > GIVE_UP_MS) {
        setStatus({ kind: 'failed', result })
        return
      }
      setStatus({ kind: 'looking', started, last: result })
    }
  }, [seat, qc])

  const go = (n: number) => { run.current++; setStatus({ kind: 'idle' }); setAt(n) }
  const undo = async () => {
    if (!seat) return
    await del(`/api/seat-walk/${encodeURIComponent(seat)}`).catch(() => undefined)
    setDone((d) => d.filter((x) => x.seat !== seat))
    previous.current = null
    setStatus({ kind: 'idle' })
    void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
  }
  const fixPlan = async (found: WalkPort) => {
    await post('/api/cables/assign', { seat, switch: found.switch, port: found.port, swap: true })
    setPlanFixed(true)
    void qc.invalidateQueries({ queryKey: qk.cables })
  }

  // Enter does the obvious next thing, so the crew can keep one hand on the cable.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' || (e.target as HTMLElement)?.closest('input, textarea, [role="combobox"]')) return
      if (status.kind === 'found') go(at + 1)
      else if (status.kind !== 'looking') void locate()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!seat) {
    return (
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm">
          <Title order={2} size="h3">{t('seatWalk.finished', { count: done.length, seats: seats.length - startAt })}</Title>
          <DoneList done={done} />
          <Button variant="default" onClick={onStop}>{t('seatWalk.again')}</Button>
        </Stack>
      </Paper>
    )
  }
  const had = seats[at].port
  const seconds = status.kind === 'looking' ? Math.max(0, Math.round((now - status.started) / 1000)) : 0
  const nextSeat = seats[at + 1]?.seat
  return (
    <Stack gap="md">
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{t('seatWalk.progress', { n: at + 1, of: seats.length, done: done.length })}</Text>
            <Button size="compact-sm" variant="subtle" onClick={onStop}>{t('seatWalk.stop')}</Button>
          </Group>
          <Title order={2} size="h1">{seat}</Title>
          <Text>{t('seatWalk.plugIn', { seat })}</Text>
          {had && status.kind === 'idle' && (
            <Text size="sm" c="dimmed">{t(had.source === 'walk' ? 'seatWalk.hadWalk' : 'seatWalk.hadCheckin', { port: portText(had) })}</Text>
          )}
          {status.kind !== 'found' && (
            <Button size="lg" mt="xs" leftSection={<IconPlugConnected size={20} />} loading={status.kind === 'looking'}
              onClick={() => void locate()}>
              {status.kind === 'failed' ? t('seatWalk.tryAgain') : t('seatWalk.locate')}
            </Button>
          )}
        </Stack>
      </Paper>

      <div aria-live="polite">
        {status.kind === 'looking' && (
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="xs">
              <Group gap="sm" wrap="nowrap">
                <Loader size="sm" />
                <Text fw={600}>{t('seatWalk.looking', { seconds })}</Text>
              </Group>
              <Text size="sm" c="dimmed">
                {status.last?.stale ? t('seatWalk.stillOld')
                  : info.switch_lookup ? t('seatWalk.lookingSwitch') : t('seatWalk.lookingMonitoring')}
              </Text>
              <Group>
                <Button size="compact-sm" variant="default" onClick={() => { run.current++; setStatus({ kind: 'idle' }) }}>
                  {t('seatWalk.cancel')}</Button>
              </Group>
            </Stack>
          </Paper>
        )}
        {status.kind === 'found' && status.result.found && (
          <Alert color="up" variant="light" radius="lg" icon={<IconCircleCheck />} title={t('seatWalk.found', { seat, port: portText(status.result.found) })}>
            <Stack gap="xs">
              <Group gap="xs">
                <Badge variant="light" color={status.result.how === 'switch' ? 'up' : 'info'} tt="none">
                  {t(status.result.how === 'switch' ? 'seatWalk.howSwitch' : 'seatWalk.howMonitoring')}</Badge>
                <Text size="sm" c="dimmed">{t('seatWalk.took', { seconds: (status.ms / 1000).toFixed(1) })}</Text>
              </Group>
              {!!status.result.replaced?.length && (
                <Text size="sm">{t('seatWalk.replaced', { seats: status.result.replaced.join(', ') })}</Text>
              )}
              {status.result.plan_seat && !planFixed && (
                <Alert color="warn" variant="light">
                  <Stack gap="xs">
                    <Text size="sm">{t('seatWalk.planSays', { port: portText(status.result.found), other: status.result.plan_seat })}</Text>
                    {canFixPlan && (
                      <Group><Button size="compact-sm" variant="default" onClick={() => void fixPlan(status.result.found!)}>
                        {t('seatWalk.fixPlan', { seat })}</Button></Group>
                    )}
                  </Stack>
                </Alert>
              )}
              {planFixed && <Text size="sm">{t('seatWalk.planFixed')}</Text>}
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" mt="xs">
                <Button size="lg" data-autofocus onClick={() => go(at + 1)}>
                  {nextSeat ? t('seatWalk.next', { seat: nextSeat }) : t('seatWalk.finish')}</Button>
                <Button size="lg" variant="default" onClick={() => void undo()}>{t('seatWalk.undo')}</Button>
              </SimpleGrid>
            </Stack>
          </Alert>
        )}
        {status.kind === 'failed' && (
          <Alert color="down" variant="light" radius="lg" icon={<IconCircleX />} role="alert"
            title={t('seatWalk.failed', { seat })}>
            <Stack gap="xs">
              <Text size="sm">
                {status.error ?? (status.result?.stale ? t('seatWalk.failedStale')
                  : status.result?.mac ? t('seatWalk.failedPort') : t('seatWalk.failedMac', { ip: status.result?.ip ?? info.ip }))}
              </Text>
              {!status.error && <Text size="sm" c="dimmed">{t('seatWalk.failedHint')}</Text>}
            </Stack>
          </Alert>
        )}
      </div>

      <Group grow>
        <Button variant="default" disabled={at === 0} onClick={() => go(at - 1)}>{t('seatWalk.back')}</Button>
        <Button variant="default" onClick={() => go(at + 1)}>{t('seatWalk.skip')}</Button>
      </Group>
      {done.length > 0 && <DoneList done={done} />}
    </Stack>
  )
}

function DoneList({ done }: { done: Done[] }) {
  const { t } = useTranslation()
  if (!done.length) return null
  return (
    <Paper withBorder radius="lg" p="sm">
      <Table verticalSpacing={4}>
        <Table.Thead><Table.Tr>
          <Table.Th>{t('seatWalk.seat')}</Table.Th><Table.Th>{t('seatWalk.port')}</Table.Th><Table.Th>{t('seatWalk.time')}</Table.Th>
        </Table.Tr></Table.Thead>
        <Table.Tbody>
          {done.map((d) => (
            <Table.Tr key={d.seat}>
              <Table.Td>{d.seat}</Table.Td><Table.Td>{portText(d.port)}</Table.Td>
              <Table.Td>{(d.ms / 1000).toFixed(1)} s</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  )
}

/** The crew's walk-through check-in: a laptop plugged in at each seat, its switch port found from
 *  its IP, kept for this event and cleared a day after it ends. */
export default function SeatWalk() {
  const { t } = useTranslation()
  const [block, setBlock] = useState('')
  const [order, setOrder] = useState('rows')
  const [skipKnown, setSkipKnown] = useState(true)
  const [walking, setWalking] = useState(false)
  const blocks = useQuery({ queryKey: qk.seatBlocks, queryFn: () => get<SeatBlock[]>('/api/seat-blocks') })
  const info = useQuery({
    queryKey: qk.seatWalk(block, order),
    queryFn: () => get<SeatWalkInfo>(`/api/seat-walk${block ? `?block=${encodeURIComponent(block)}&order=${order}` : ''}`),
  })
  const seats = info.data?.seats ?? []
  const firstOpen = skipKnown ? seats.findIndex((s) => !s.port) : 0
  const known = seats.filter((s) => s.port).length
  const d = info.data
  return (
    <Layout title={t('seatWalk.title')} back={{ href: '/checkins', label: t('crewCheckin.title') }}>
      <PageHead title={t('seatWalk.title')} desc={walking ? undefined : t('seatWalk.intro')} />
      {walking && d && seats.length ? (
        <Walk info={d} seats={seats} startAt={Math.max(0, firstOpen)} onStop={() => setWalking(false)} />
      ) : (
        <Stack gap="md">
          {d && !d.ip_allowed && <Alert color="warn">{t('seatWalk.notSeatNetwork', { ip: d.ip })}</Alert>}
          {d && !d.switch_lookup && !d.monitoring && <Alert color="down">{t('seatWalk.noLookup')}</Alert>}
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="sm">
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                <Select label={t('seatWalk.block')} required searchable value={block || null} onChange={(v) => setBlock(v ?? '')}
                  data={(blocks.data ?? []).map((b) => ({ value: b.id, label: `${b.name || '–'} (${b.cols * b.rows})` }))} />
                <Select label={t('seatWalk.order')} allowDeselect={false} value={order} onChange={(v) => setOrder(v ?? 'rows')}
                  data={[{ value: 'rows', label: t('seatWalk.orderRows') }, { value: 'snake', label: t('seatWalk.orderSnake') }]} />
              </SimpleGrid>
              {known > 0 && (
                <Checkbox checked={skipKnown} onChange={(e) => setSkipKnown(e.currentTarget.checked)}
                  label={t('seatWalk.skipKnown', { count: known })} />
              )}
              {info.error && <Alert color="down" role="alert">{info.error.message}</Alert>}
              <Button disabled={!seats.length || firstOpen < 0} onClick={() => setWalking(true)}>
                {!seats.length ? t('seatWalk.pick') : firstOpen < 0 ? t('seatWalk.allKnown')
                  : t('seatWalk.start', { seat: seats[Math.max(0, firstOpen)].seat })}
              </Button>
            </Stack>
          </Paper>
          {d && (
            <Paper withBorder radius="lg" p="lg">
              <Stack gap={6}>
                <Text size="sm">{t('seatWalk.laptop', { ip: d.ip })}</Text>
                <Group gap="xs">
                  <Badge variant="light" color={d.switch_lookup ? 'up' : 'gray'} tt="none">
                    {t(d.switch_lookup ? 'seatWalk.switchOn' : 'seatWalk.switchOff')}</Badge>
                  <Badge variant="light" color={d.monitoring ? 'up' : 'gray'} tt="none">
                    {t(d.monitoring ? 'seatWalk.monitoringOn' : 'seatWalk.monitoringOff')}</Badge>
                </Group>
                <Text size="sm" c="dimmed">{t('seatWalk.kept', { event: d.event.name || t('seatWalk.thisEvent'), hours: d.keep_hours })}</Text>
                <Text size="sm" c="dimmed">{t('seatWalk.portfast')}</Text>
              </Stack>
            </Paper>
          )}
        </Stack>
      )}
    </Layout>
  )
}
