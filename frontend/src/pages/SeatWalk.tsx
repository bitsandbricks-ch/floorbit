import { Alert, Badge, Button, Checkbox, Code, Group, Loader, Paper, Select, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconCircleCheck, IconCircleX, IconPlugConnected } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { useLiveEvent } from '@/api/live'
import type { SeatLocated, SeatWalker, SeatWalkHello, SeatWalkInfo, WalkPort } from '@/api/types'
import { Layout } from '@/components/Layout'
import { DataTable } from '@/components/DataTable'
import { PageHead } from '@/components/PageHead'
import { RowsSelect } from '@/components/RowsSelect'
import { HallRows } from './seatWalk/HallRows'
import { leave } from './seatWalkLeave'

/** How long the page keeps asking before it says the lookup failed. Each request tries about 20 s;
 *  a monitoring source that only polls the MAC tables every minute or so needs a few of them. */
export const GIVE_UP_MS = 90_000
/** With the laptop known at once (through the agent, or a typed MAC) the page watches for the cable
 *  by itself: it asks again every few seconds until the laptop shows up on a new port (#1000). */
export const WATCH_EVERY_MS = 3_000
export const WATCH_FOR_MS = 5 * 60_000
/** After a seat is found the walk moves on by itself, unless there is something to read. */
export const NEXT_AFTER_MS = 2_000

type Done = { seat: string; port: WalkPort; how: SeatLocated['how']; ms: number }
type Status =
  | { kind: 'idle' }
  | { kind: 'identifying' }
  | { kind: 'looking'; started: number; last?: SeatLocated; waiting?: boolean }
  | { kind: 'found'; result: SeatLocated; ms: number }
  | { kind: 'failed'; result?: SeatLocated; error?: string }

const portText = (p: WalkPort) => `${p.switch} ${p.port}`

/** A MAC as the crew might type it: colons, dashes, dots or nothing. */
export const MAC_RE = /^([0-9a-f]{2}[:-]?){5}[0-9a-f]{2}$|^([0-9a-f]{4}\.){2}[0-9a-f]{4}$/i

/** What survives the trip through the local agent: the page leaves for the agent's hello and
 *  comes back with ?hello=<code>. Only in this tab, never shared. */
const KEPT = 'floorbit-seat-walk'
export type Kept = {
  rows: string[]; order: string; at: number; done: Done[]; previous: WalkPort | null
  laptop: { mac: string; ip: string } | null; mac: string; walker?: string | null
}
function readKept(): Kept | null {
  try { return JSON.parse(sessionStorage.getItem(KEPT) ?? 'null') as Kept | null } catch { return null }
}
function keep(k: Kept | null) {
  try { if (k) sessionStorage.setItem(KEPT, JSON.stringify(k)); else sessionStorage.removeItem(KEPT) } catch { /* private window */ }
}
/** Read once per page load: the page may mount more than once while the app starts, and the
 *  first mount takes the code off the address. */
let cameBack: { hello: string; kept: Kept } | null = null
function comingBack() {
  if (new URLSearchParams(window.location.search).has('hello')) {
    const hello = takeHello()
    const kept = readKept()
    cameBack = hello && kept ? { hello, kept } : null
  }
  return cameBack
}

/** The code the agent sent the laptop back with, taken off the address so a reload doesn't reuse it. */
function takeHello(): string | null {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('hello')
  if (!code) return null
  params.delete('hello')
  const rest = params.toString()
  window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}`)
  return code
}

/** The walk: one seat at a time. Plug in, Locate, see the port (or why not), next seat. */
function Walk({ info, seats, startAt, rows, order, typedMac, walker, resumed, onStop }: {
  info: SeatWalkInfo; seats: { seat: string; port: WalkPort | null }[]; startAt: number
  rows: string[]; order: string; typedMac: string; walker: string | null
  resumed: { kept: Kept; hello: string } | null; onStop: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canFixPlan = useCan('floorplan.edit')
  const [at, setAt] = useState(resumed ? resumed.kept.at : startAt)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [done, setDone] = useState<Done[]>(resumed?.kept.done ?? [])
  const [now, setNow] = useState(() => Date.now())
  const [planFixed, setPlanFixed] = useState(false)
  const run = useRef(0)                      // a new Locate, Cancel or seat drops answers of the old one
  const laptop = useRef<{ mac: string; ip: string } | null>(resumed?.kept.laptop ?? null)
  const previous = useRef<WalkPort | null>(resumed?.kept.previous ?? null)
  const seat = seats[at]?.seat
  // Known at once (through the agent, or a typed MAC): no Locate to press, the page watches.
  const auto = Boolean(typedMac || info.through_agent)

  useEffect(() => {
    if (status.kind !== 'looking') return
    const timer = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [status.kind])

  const locate = useCallback(async (hello?: string) => {
    if (!seat) return
    const mine = ++run.current
    if (!typedMac && !hello) {
      // Always through the local agent: it sees the laptop's own address, Floorbit may not
      // (a proxy, NAT, a hosted Floorbit). The laptop gets a new address at some seats, so every seat.
      setStatus({ kind: 'identifying' })
      try {
        const made = await post<SeatWalkHello>('/api/seat-walk/hello')
        if (run.current !== mine) return
        if (made.ip || !made.url) {
          // Opened through an agent: it already named this laptop, no trip needed.
          void locate(made.hello)
          return
        }
        keep({ rows, order, at, done, previous: previous.current, laptop: laptop.current, mac: typedMac, walker })
        const back = `${window.location.origin}${window.location.pathname}?hello=${encodeURIComponent(made.hello)}`
        leave.to(`${made.url}?back=${encodeURIComponent(back)}`)
      } catch (e) {
        if (run.current === mine) setStatus({ kind: 'failed', error: e instanceof ApiError ? e.message : String(e) })
      }
      return
    }
    const started = Date.now()
    setPlanFixed(false)
    setNow(started)
    setStatus({ kind: 'looking', started })
    for (;;) {
      let result: SeatLocated
      try {
        result = await post<SeatLocated>('/api/seat-walk/locate', typedMac
          ? { seat, previous: previous.current, mac: typedMac, mac_typed: true }
          : { seat, previous: previous.current, hello, mac: laptop.current?.mac, mac_ip: laptop.current?.ip })
      } catch (e) {
        if (run.current === mine) setStatus({ kind: 'failed', error: e instanceof ApiError ? e.message : String(e) })
        return
      }
      if (run.current !== mine) return
      if (result.mac && result.ip) laptop.current = { mac: result.mac, ip: result.ip }
      if (result.ok && result.found) {
        previous.current = result.found
        const row: Done = { seat, port: result.found, how: result.how, ms: Date.now() - started }
        setDone((d) => [row, ...d.filter((x) => x.seat !== seat)])
        setStatus({ kind: 'found', result, ms: row.ms })
        void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
        return
      }
      if (auto && Date.now() - started < WATCH_FOR_MS) {
        // Not on a new port yet: the cable isn't in, or the switch hasn't seen the laptop. Ask again.
        setStatus({ kind: 'looking', started, last: result, waiting: true })
        await new Promise((r) => window.setTimeout(r, WATCH_EVERY_MS))
        if (run.current !== mine) return
        continue
      }
      if (!result.retry || Date.now() - started > GIVE_UP_MS) {
        setStatus({ kind: 'failed', result })
        return
      }
      setStatus({ kind: 'looking', started, last: result })
    }
  }, [seat, qc, typedMac, rows, order, at, done, auto, walker])

  // Back from the agent with this seat's code: carry on where the crew pressed Locate.
  const resumedOnce = useRef(false)
  useEffect(() => {
    if (!resumed || resumedOnce.current) return
    resumedOnce.current = true
    keep(null)
    cameBack = null
    void locate(resumed.hello)
  }, [resumed, locate])

  const go = (n: number) => { run.current++; setStatus({ kind: 'idle' }); setAt(n) }

  // Each new seat starts watching by itself, once: after Cancel or Undo the crew presses Locate.
  const autoFor = useRef<number | null>(resumed ? resumed.kept.at : null)
  useEffect(() => {
    if (!auto || !seat || status.kind !== 'idle' || autoFor.current === at) return
    autoFor.current = at
    void locate()
  }, [auto, seat, at, status.kind, locate])

  // Found with nothing to read: on to the next seat by itself; the list below keeps Undo.
  const quiet = status.kind === 'found' && !status.result.plan_seat && !status.result.replaced?.length
  useEffect(() => {
    if (!auto || !quiet) return
    const timer = window.setTimeout(() => { run.current++; setStatus({ kind: 'idle' }); setAt(at + 1) }, NEXT_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [auto, quiet, at])

  // Where this walker is, for the others' overview; also says the walk is still on.
  useEffect(() => {
    if (!walker) return
    const say = () => void put(`/api/seat-walk/walkers/${walker}`, { seat: seat ?? null }).catch(() => undefined)
    say()
    const timer = window.setInterval(say, 60_000)
    return () => window.clearInterval(timer)
  }, [walker, seat])
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
      else if (status.kind !== 'looking' && status.kind !== 'identifying') void locate()
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
          <Text>{t(auto ? 'seatWalk.plugInAuto' : 'seatWalk.plugIn', { seat })}</Text>
          {typedMac && <Text size="sm" c="dimmed">{t('seatWalk.usingMac', { mac: typedMac })}</Text>}
          {had && status.kind === 'idle' && (
            <Text size="sm" c="dimmed">{t(had.source === 'walk' ? 'seatWalk.hadWalk' : 'seatWalk.hadCheckin', { port: portText(had) })}</Text>
          )}
          {status.kind !== 'found' && !(auto && (status.kind === 'looking' || status.kind === 'identifying')) && (
            <Button size="lg" mt="xs" leftSection={<IconPlugConnected size={20} />} loading={status.kind === 'looking' || status.kind === 'identifying'}
              onClick={() => void locate()}>
              {status.kind === 'failed' ? t('seatWalk.tryAgain') : t('seatWalk.locate')}
            </Button>
          )}
        </Stack>
      </Paper>

      <div aria-live="polite">
        {status.kind === 'identifying' && (
          <Paper withBorder radius="lg" p="lg">
            <Group gap="sm" wrap="nowrap"><Loader size="sm" /><Text fw={600}>{t('seatWalk.identifying')}</Text></Group>
          </Paper>
        )}
        {status.kind === 'looking' && (
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="xs">
              <Group gap="sm" wrap="nowrap">
                <Loader size="sm" />
                <Text fw={600}>{status.waiting ? t('seatWalk.waiting', { seat }) : t('seatWalk.looking', { seconds })}</Text>
              </Group>
              <Text size="sm" c="dimmed">
                {status.waiting ? t('seatWalk.waitingHint')
                  : status.last?.stale ? t('seatWalk.stillOld')
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
                <Badge variant="light" color={status.result.how === 'switch' || status.result.how === 'snmp' ? 'up' : 'info'} tt="none">
                  {t(status.result.how === 'switch' || status.result.how === 'snmp' ? 'seatWalk.howSwitch' : 'seatWalk.howMonitoring')}</Badge>
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
              {auto && quiet && nextSeat && <Text size="sm" c="dimmed">{t('seatWalk.nextSoon', { seat: nextSeat })}</Text>}
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
                  : status.result?.mac ? t('seatWalk.failedPort') : t('seatWalk.failedMac', { ip: status.result?.ip ?? '?' }))}
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
    <DataTable rows={done} rowKey={(d) => d.seat} label={t('seatWalk.doneList')} urlState={false} pageSize={0} density="compact"
      columns={[
        { id: 'seat', header: t('seatWalk.seat'), cell: (d) => d.seat },
        { id: 'port', header: t('seatWalk.port'), cell: (d) => portText(d.port) },
        { id: 'time', header: t('seatWalk.time'), numeric: true, cell: (d) => `${(d.ms / 1000).toFixed(1)} s` },
      ]} />
  )
}

/** The crew's walk-through check-in: a laptop plugged in at each seat, its switch port found from
 *  its IP, kept for this event and cleared a day after it ends. */
export default function SeatWalk() {
  const { t } = useTranslation()
  // Back from the local agent: the walk picks up at the seat it left.
  const [resumed] = useState(comingBack)
  const [rows, setRows] = useState<string[]>(resumed?.kept.rows ?? [])
  const [order, setOrder] = useState(resumed?.kept.order ?? 'rows')
  const [skipKnown, setSkipKnown] = useState(true)
  const [walking, setWalking] = useState(!!resumed)
  const [mac, setMac] = useState(resumed?.kept.mac ?? '')
  const [walker, setWalker] = useState<string | null>(resumed?.kept.walker ?? null)
  const [held, setHeld] = useState<string[] | null>(null)       // who walks one of the picked rows
  const [starting, setStarting] = useState(false)
  const qc = useQueryClient()
  useLiveEvent('seat-walk.changed', () => void qc.invalidateQueries({ queryKey: qk.seatWalkAll }))
  const macOk = !mac.trim() || MAC_RE.test(mac.trim())
  const info = useQuery({
    queryKey: qk.seatWalk(rows.join(','), order),
    queryFn: () => get<SeatWalkInfo>(`/api/seat-walk${rows.length ? `?rows=${encodeURIComponent(rows.join(','))}&order=${order}` : ''}`),
  })
  const seats = info.data?.seats ?? []
  const firstOpen = skipKnown ? seats.findIndex((s) => !s.port) : 0
  const known = seats.filter((s) => s.port).length
  const d = info.data
  // Start claims the rows, so two walkers don't walk the same row; a row someone left can be taken.
  const start = async (take = false) => {
    setStarting(true)
    try {
      const made = await post<SeatWalker>('/api/seat-walk/walkers', { rows, take })
      setWalker(made.id); setHeld(null); setWalking(true)
      void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setHeld((e.data.held as string[] | undefined) ?? [])
      else throw e
    } finally {
      setStarting(false)
    }
  }
  const stop = () => {
    if (walker) void del(`/api/seat-walk/walkers/${walker}`).catch(() => undefined)
    keep(null); cameBack = null; setWalker(null); setWalking(false)
    void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
  }
  return (
    <Layout title={t('seatWalk.title')} back={{ href: '/checkins', label: t('crewCheckin.title') }}>
      <PageHead title={t('seatWalk.title')} desc={walking ? undefined : t('seatWalk.intro')} />
      {walking && d && seats.length ? (
        <Walk info={d} seats={seats} startAt={Math.max(0, firstOpen)} rows={rows} order={order}
          typedMac={macOk ? mac.trim() : ''} walker={walker} resumed={resumed} onStop={stop} />
      ) : (
        <Stack gap="md">
          {d && !d.agent_url && !d.through_agent && !mac.trim() && <Alert color="warn">{t('seatWalk.noAgent')}</Alert>}
          {d && !d.switch_lookup && !d.monitoring && <Alert color="down">{t('seatWalk.noLookup')}</Alert>}
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="sm">
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                <RowsSelect label={t('seatWalk.rows')} required value={rows} onChange={setRows} />
                <Select label={t('seatWalk.order')} allowDeselect={false} value={order} onChange={(v) => setOrder(v ?? 'rows')}
                  data={[{ value: 'rows', label: t('seatWalk.orderRows') }, { value: 'snake', label: t('seatWalk.orderSnake') }]} />
              </SimpleGrid>
              {known > 0 && (
                <Checkbox checked={skipKnown} onChange={(e) => setSkipKnown(e.currentTarget.checked)}
                  label={t('seatWalk.skipKnown', { count: known })} />
              )}
              <TextInput label={t('seatWalk.mac')} description={t('seatWalk.macHelp')} placeholder="02:00:00:00:00:10"
                value={mac} onChange={(e) => setMac(e.currentTarget.value)} maxLength={17}
                error={macOk ? undefined : t('seatWalk.macBad')} autoComplete="off" spellCheck={false} />
              {info.error && <Alert color="down" role="alert">{info.error.message}</Alert>}
              {held && (
                <Alert color="warn" role="alert">
                  <Stack gap="xs">
                    <Text size="sm">{t('seatWalk.held', { who: held.join(', ') || '?' })}</Text>
                    <Group><Button size="compact-sm" variant="default" onClick={() => void start(true)}>{t('seatWalk.takeOver')}</Button></Group>
                  </Stack>
                </Alert>
              )}
              <Button disabled={!seats.length || firstOpen < 0 || !macOk} loading={starting} onClick={() => void start()}>
                {!seats.length ? t('seatWalk.pick') : firstOpen < 0 ? t('seatWalk.allKnown')
                  : t('seatWalk.start', { seat: seats[Math.max(0, firstOpen)].seat })}
              </Button>
            </Stack>
          </Paper>
          {d?.hall && <HallRows rows={d.hall} mine={walker}
            onPick={(id) => setRows((r) => (r.includes(id) ? r : [...r, id]))} />}
          {d && (
            <Paper withBorder radius="lg" p="lg">
              <Stack gap={6}>
                <Text size="sm">{d.agent_url ? <>{t('seatWalk.agentAt')} <Code>{d.agent_url}</Code></> : t('seatWalk.agentNone')}</Text>
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
