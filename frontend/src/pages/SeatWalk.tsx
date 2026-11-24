import { Alert, Badge, Button, Checkbox, Grid, Group, Loader, Paper, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { IconCircleCheck, IconCircleX, IconPlayerPause, IconPlugConnected } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AreaDrift } from './switchAreas/AreaDrift'
import { ApiError, del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { useLiveEvent } from '@/api/live'
import type { SeatLocated, SeatWalkHello, WalkPort } from '@/api/types'
import type { KeptWalk, SeatWalkOverview, WalkSeat } from '@/api/seatWalk'
import { Layout } from '@/components/Layout'
import { DataTable, PageHead } from '@bitsandbricks/ui'
import { RowsSelect } from '@/components/RowsSelect'
import { HallRows } from './seatWalk/HallRows'
import { SeatMarker } from './seatWalk/SeatMarker'
import { SeatStrip } from './seatWalk/SeatStrip'
import { rowTitle } from './seatWalk/rowTitle'
import { FlowStrip, LaptopStrip, TraceConsole } from './seatWalk/Trace'
import { mergeSteps, newRun, type TraceEvent, type TraceStep } from '@/api/seatWalkTrace'
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

type Done = { seat: string; port: WalkPort; how?: SeatLocated['how']; ms: number | null }
type Status =
  | { kind: 'idle' }
  | { kind: 'identifying' }
  | { kind: 'looking'; started: number; last?: SeatLocated; waiting?: boolean }
  | { kind: 'found'; result: SeatLocated; ms: number }
  | { kind: 'failed'; result?: SeatLocated; error?: string }

const portText = (p: WalkPort) => `${p.switch} ${p.port}`
/** The kept walk's seats as the page lists them, newest first. */
const doneOf = (w: KeptWalk): Done[] => (w.done ?? []).map((d) => ({ seat: d.seat, port: { switch: d.switch, port: d.port }, ms: d.ms }))
/** The next seat from ``n`` a walk goes to: marked seats wait until someone picks them on purpose. */
function nextSeat(seats: WalkSeat[], n: number) {
  let i = Math.max(0, n)
  while (i < seats.length && seats[i].mark) i++
  return i
}

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
function Walk({ info, seats, startAt, rows, order, typedMac, walker, resumed, initialDone, jump, onPause, onEnd, onLost }: {
  info: SeatWalkOverview; seats: WalkSeat[]; startAt: number
  rows: string[]; order: string; typedMac: string; walker: string | null
  resumed: { kept: Kept; hello: string } | null; initialDone: Done[]
  jump: { n: number; nonce: number } | null
  onPause: () => void; onEnd: () => void; onLost: (why: string) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canFixPlan = useCan('floorplan.edit')
  const canMark = useCan('seats.edit')
  const [at, setAt] = useState(resumed ? resumed.kept.at : startAt)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [done, setDone] = useState<Done[]>(resumed?.kept.done ?? initialDone)
  const [autoNext, setAutoNext] = useState(true)
  const [now, setNow] = useState(() => Date.now())
  const [planFixed, setPlanFixed] = useState(false)
  const run = useRef(0)                      // a new Locate, Cancel or seat drops answers of the old one
  const laptop = useRef<{ mac: string; ip: string } | null>(resumed?.kept.laptop ?? null)
  const previous = useRef<WalkPort | null>(resumed?.kept.previous ?? null)
  // The live trace of the current Locate (issue #1359) and the laptop as last seen (issue #1358).
  const [steps, setSteps] = useState<TraceStep[]>([])
  const traceRun = useRef('')
  const [seen, setSeen] = useState<{ ip: string | null; mac: string | null; agent: string | null }>(
    { ip: resumed?.kept.laptop?.ip ?? null, mac: typedMac || (resumed?.kept.laptop?.mac ?? null), agent: null })
  useLiveEvent('seat-walk.trace', (data) => {
    const e = data as TraceEvent
    if (e?.run && e.run === traceRun.current && e.step) setSteps((have) => mergeSteps(have, [e.step]))
  })
  const seat = seats[at]?.seat
  // Known at once (through the agent, or a typed MAC): no Locate to press, the page watches.
  const auto = Boolean(typedMac || info.through_agent)

  useEffect(() => {
    if (status.kind !== 'looking') return
    const timer = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [status.kind])

  // A seat that wasn't found stays with the kept walk, so whoever continues it comes back to it.
  const fail = useCallback((next: Extract<Status, { kind: 'failed' }>) => {
    setStatus(next)
    if (!walker || !seat) return
    const why = next.error ?? (next.result?.stale ? 'stale' : next.result?.mac ? 'no port' : 'no MAC')
    void put(`/api/seat-walk/walkers/${walker}`, { seat, failed: { seat, why } })
      .then(() => qc.invalidateQueries({ queryKey: qk.seatWalkAll })).catch(() => undefined)
  }, [walker, seat, qc])

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
        if (run.current === mine) fail({ kind: 'failed', error: e instanceof ApiError ? e.message : String(e) })
      }
      return
    }
    const started = Date.now()
    traceRun.current = newRun()
    setSteps([])
    setPlanFixed(false)
    setNow(started)
    setStatus({ kind: 'looking', started })
    for (;;) {
      let result: SeatLocated
      try {
        result = await post<SeatLocated>('/api/seat-walk/locate', typedMac
          ? { seat, previous: previous.current, mac: typedMac, mac_typed: true, run: traceRun.current, walker }
          : { seat, previous: previous.current, hello, mac: laptop.current?.mac, mac_ip: laptop.current?.ip, run: traceRun.current, walker })
      } catch (e) {
        if (run.current === mine) fail({ kind: 'failed', error: e instanceof ApiError ? e.message : String(e) })
        return
      }
      if (run.current !== mine) return
      if (result.trace?.length) setSteps((have) => mergeSteps(have, result.trace ?? []))
      setSeen((was) => ({ ip: result.ip ?? was.ip, mac: result.mac ?? was.mac, agent: result.agent ?? was.agent }))
      if (result.mac && result.ip) laptop.current = { mac: result.mac, ip: result.ip }
      if (result.ok && result.found) {
        previous.current = result.found
        const ms = Date.now() - started
        const row: Done = { seat, port: result.found, how: result.how, ms }
        setDone((d) => [row, ...d.filter((x) => x.seat !== seat)])
        setStatus({ kind: 'found', result, ms })
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
        fail({ kind: 'failed', result })
        return
      }
      setStatus({ kind: 'looking', started, last: result })
    }
  }, [seat, qc, typedMac, rows, order, at, done, auto, walker, fail])

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
  // On to the next seat that isn't marked; a seat picked in the strip or the row list is checked anyway.
  const onward = () => go(nextSeat(seats, at + 1))
  const jumped = useRef(jump?.nonce ?? 0)
  useEffect(() => {
    if (!jump || jump.nonce === jumped.current) return
    jumped.current = jump.nonce
    run.current++; setStatus({ kind: 'idle' }); setAt(jump.n)
  }, [jump])

  // Each new seat starts watching by itself, once: after Cancel or Undo the crew presses Locate.
  const autoFor = useRef<number | null>(resumed ? resumed.kept.at : null)
  useEffect(() => {
    if (!auto || !seat || status.kind !== 'idle' || autoFor.current === at) return
    autoFor.current = at
    void locate()
  }, [auto, seat, at, status.kind, locate])

  // Found with nothing to read: on to the next seat by itself; the list below keeps Undo.
  const quiet = status.kind === 'found' && !status.result.plan_seat && !status.result.replaced?.length
  const onwardAt = nextSeat(seats, at + 1)
  useEffect(() => {
    if (!auto || !quiet || !autoNext) return
    const timer = window.setTimeout(() => { run.current++; setStatus({ kind: 'idle' }); setAt(onwardAt) }, NEXT_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [auto, quiet, autoNext, onwardAt])

  // Where this walker is, for the others' overview; also says the walk is still on.
  useEffect(() => {
    if (!walker) return
    const say = () => void put(`/api/seat-walk/walkers/${walker}`, { seat: seat ?? null }).catch((e: unknown) => {
      // Someone took this walk over, or it ended elsewhere: this page stops writing to it.
      if (!(e instanceof ApiError)) return
      if (e.status === 409) onLost(t('seatWalkRows.takenOver', { who: (e.data.held as string[] | undefined)?.join(', ') || '?' }))
      else if (e.status === 404) onLost(t('seatWalkRows.lost'))
    })
    say()
    const timer = window.setInterval(say, 60_000)
    return () => window.clearInterval(timer)
  }, [walker, seat, onLost, t])
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
      if (status.kind === 'found') onward()
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
          {seats.some((s) => s.mark) && <Text size="sm" c="dimmed">{t('seatWalkRows.skipsMarked')}</Text>}
          <SeatStrip seats={seats} at={at} onPick={go} />
          <Group grow>
            <Button variant="default" onClick={onEnd}>{t('seatWalkRows.end')}</Button>
            <Button variant="default" onClick={() => go(Math.max(0, at - 1))}>{t('seatWalk.back')}</Button>
          </Group>
        </Stack>
      </Paper>
    )
  }
  const had = seats[at].port
  const seconds = status.kind === 'looking' ? Math.max(0, Math.round((now - status.started) / 1000)) : 0
  const upNext = seats[onwardAt]?.seat
  const here = seats[at]
  const running = status.kind === 'looking' || status.kind === 'identifying'
  return (
    <Stack gap="md">
      <LaptopStrip agentUrl={info.agent_url} ip={seen.ip} mac={seen.mac} agent={seen.agent} />
      <Paper withBorder radius="lg" p="md"><SeatStrip seats={seats} at={at} onPick={go} /></Paper>
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{t('seatWalk.progress', { n: at + 1, of: seats.length, done: done.length })}</Text>
            <Group gap="xs">
              <Button size="compact-sm" variant="default" leftSection={<IconPlayerPause size={14} />} onClick={onPause}
                title={t('seatWalkRows.pauseHint')}>{t('seatWalkRows.pause')}</Button>
              <Button size="compact-sm" variant="subtle" onClick={onEnd}>{t('seatWalkRows.end')}</Button>
            </Group>
          </Group>
          <Title order={2} size="h1">{seat}</Title>
          {here.failed && !here.port && <Text size="sm" c="down">{t('seatWalkRows.failedBefore', { who: here.failed.who })}</Text>}
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
          {canMark && status.kind !== 'found' && (
            <SeatMarker key={seat} seat={seat} mark={here.mark}
              onChanged={() => void qc.invalidateQueries({ queryKey: qk.seatWalkAll })} onMarked={onward} />
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
              <AreaDrift drift={status.result.area_drift} />
              {auto && quiet && autoNext && upNext && <Text size="sm" c="dimmed">{t('seatWalk.nextSoon', { seat: upNext })}</Text>}
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" mt="xs">
                <Button size="lg" data-autofocus onClick={onward}>
                  {upNext ? t('seatWalk.next', { seat: upNext }) : t('seatWalk.finish')}</Button>
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

      {(steps.length > 0 || running) && (
        <>
          <Paper withBorder radius="lg" p="md"><FlowStrip steps={steps} running={running} seat={seat} /></Paper>
          <TraceConsole steps={steps} running={running} />
        </>
      )}
      <Group grow>
        <Button variant="default" disabled={at === 0} onClick={() => go(at - 1)}>{t('seatWalk.back')}</Button>
        <Button variant="default" onClick={onward}>{t('seatWalk.skip')}</Button>
      </Group>
      {auto && <Switch size="sm" checked={autoNext} onChange={(e) => setAutoNext(e.currentTarget.checked)} label={t('seatWalkRows.autoNext')} />}
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
        { id: 'time', header: t('seatWalk.time'), numeric: true, cell: (d) => (d.ms == null ? '' : `${(d.ms / 1000).toFixed(1)} s`) },
      ]} />
  )
}

/** The crew's walk-through check-in: a laptop plugged in at each seat, its switch port found from
 *  its IP, kept for this event and cleared a day after it ends. Each walk is kept on the server, so
 *  its walker continues it later and others can take it over (issue #1356); the hall's rows sit
 *  beside it (layout D1). */
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
  const [startSeat, setStartSeat] = useState<string | null>(null)
  const [initialDone, setInitialDone] = useState<Done[]>([])
  const [jump, setJump] = useState<{ n: number; nonce: number } | null>(null)
  const [lost, setLost] = useState<string | null>(null)
  const qc = useQueryClient()
  useLiveEvent('seat-walk.changed', () => void qc.invalidateQueries({ queryKey: qk.seatWalkAll }))
  const macOk = !mac.trim() || MAC_RE.test(mac.trim())
  const info = useQuery({
    queryKey: qk.seatWalk(rows.join(','), order),
    queryFn: () => get<SeatWalkOverview>(`/api/seat-walk${rows.length ? `?rows=${encodeURIComponent(rows.join(','))}&order=${order}` : ''}`),
  })
  const d = info.data
  const seats = d?.seats ?? []
  const firstOpen = skipKnown ? seats.findIndex((s) => !s.port && !s.mark) : nextSeat(seats, 0)
  const known = seats.filter((s) => s.port).length
  const me = d?.me
  const hall = d?.hall ?? []
  const names = new Map(hall.map((r) => [r.id, rowTitle(t, r)]))
  const rowsText = (ids: string[]) => ids.map((r) => names.get(r) ?? r).join(', ')
  // My newest walk that stopped (a break, a closed tab): continued here, where it got to.
  const paused = walking ? undefined : d?.walks?.find((w) => w.user === me && !w.active)

  const walkOn = (w: KeptWalk) => {
    setRows(w.rows); setOrder(w.order); setWalker(w.id); setStartSeat(w.seat); setInitialDone(doneOf(w))
    setHeld(null); setLost(null); setJump(null); setWalking(true)
    void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
  }
  const onClaimError = (e: unknown) => {
    if (e instanceof ApiError && e.status === 409) setHeld((e.data.held as string[] | undefined) ?? [])
    else if (e instanceof ApiError) setLost(e.message)
    else throw e
  }
  // Start claims the rows, so two walkers don't walk the same row; a row someone left can be taken.
  const start = async (take = false) => {
    setStarting(true)
    try {
      walkOn(await post<KeptWalk>('/api/seat-walk/walkers', { rows, take, order }))
    } catch (e) {
      onClaimError(e)
    } finally {
      setStarting(false)
    }
  }
  const resume = async (w: KeptWalk) => {
    try { walkOn(await put<KeptWalk>(`/api/seat-walk/walkers/${w.id}`, { seat: w.seat })) } catch (e) { onClaimError(e) }
  }
  const takeOver = async (w: KeptWalk) => {
    try { walkOn(await post<KeptWalk>(`/api/seat-walk/walkers/${w.id}/take`)) } catch (e) { onClaimError(e) }
  }
  const leaveWalk = () => {
    keep(null); cameBack = null; setWalker(null); setWalking(false); setStartSeat(null); setJump(null)
    void qc.invalidateQueries({ queryKey: qk.seatWalkAll })
  }
  const end = () => {
    if (walker) void del(`/api/seat-walk/walkers/${walker}`).catch(() => undefined)
    leaveWalk()
  }
  const pause = () => {
    if (walker) void put(`/api/seat-walk/walkers/${walker}`, { paused: true }).catch(() => undefined)
    leaveWalk()
  }
  const onLost = useCallback((why: string) => {
    keep(null); cameBack = null; setWalker(null); setWalking(false); setLost(why)
  }, [])
  // A row picked in the list: walking, the walk jumps to its first seat; else it is the row to walk.
  const pickRow = (id: string) => {
    if (!walking) { setRows([id]); return }
    const k = (d?.rows ?? rows).indexOf(id)
    if (k < 0) return
    const before = (d?.rows ?? rows).slice(0, k).reduce((n, r) => n + (hall.find((h) => h.id === r)?.seats ?? 0), 0)
    setJump((j) => ({ n: before, nonce: (j?.nonce ?? 0) + 1 }))
  }
  const startAt = startSeat ? Math.max(0, seats.findIndex((s) => s.seat === startSeat)) : Math.max(0, firstOpen)

  const main = walking && d && seats.length ? (
    <Walk key={walker ?? 'walk'} info={d} seats={seats} startAt={startAt} rows={rows} order={order}
      typedMac={macOk ? mac.trim() : ''} walker={walker} resumed={resumed} initialDone={initialDone}
      jump={jump} onPause={pause} onEnd={end} onLost={onLost} />
  ) : (
    <Stack gap="md">
      {lost && <Alert color="warn" role="alert" withCloseButton onClose={() => setLost(null)}>{lost}</Alert>}
      {paused && (
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="xs">
            <Title order={2} size="h4">{t('seatWalkRows.continueTitle')}</Title>
            <Text size="sm">{paused.seat
              ? t('seatWalkRows.continueText', { rows: rowsText(paused.rows), done: paused.done.length, seat: paused.seat })
              : t('seatWalkRows.continueTextNoSeat', { rows: rowsText(paused.rows), done: paused.done.length })}</Text>
            <Group gap="xs">
              <Button onClick={() => void resume(paused)}>{t('seatWalkRows.continue')}</Button>
              <Button variant="default" onClick={() => {
                void del(`/api/seat-walk/walkers/${paused.id}`).then(() => qc.invalidateQueries({ queryKey: qk.seatWalkAll }))
              }}>{t('seatWalkRows.end')}</Button>
            </Group>
          </Stack>
        </Paper>
      )}
      {d && !d.agent_url && !d.through_agent && !mac.trim() && <Alert color="warn">{t('seatWalk.noAgent')}</Alert>}
      {d && !d.switch_lookup && !d.monitoring && <Alert color="down">{t('seatWalk.noLookup')}</Alert>}
      {d && <LaptopStrip agentUrl={d.agent_url} ip={null} mac={mac.trim() && macOk ? mac.trim() : null} agent={null} />}
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
          <Button disabled={!seats.length || firstOpen < 0 || firstOpen >= seats.length || !macOk} loading={starting} onClick={() => void start()}>
            {!seats.length ? t('seatWalk.pick') : firstOpen < 0 || firstOpen >= seats.length ? t('seatWalk.allKnown')
              : t('seatWalk.start', { seat: seats[firstOpen].seat })}
          </Button>
        </Stack>
      </Paper>
      {d && (
        <Paper withBorder radius="lg" p="lg">
          <Stack gap={6}>
            {!d.agent_url && <Text size="sm">{t('seatWalk.agentNone')}</Text>}
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
  )
  return (
    <Layout title={t('seatWalk.title')} back={{ href: '/checkins', label: t('crewCheckin.title') }}>
      <PageHead title={t('seatWalk.title')} desc={walking ? undefined : t('seatWalk.intro')} />
      {hall.length ? (
        <Grid gap="md">
          <Grid.Col span={{ base: 12, md: 4, xl: 3 }} order={{ base: 2, md: 1 }}>
            <HallRows rows={hall} walks={d?.walks ?? []} me={me} mine={walker} selected={rows[0] ?? null}
              onSelect={pickRow} onTake={(w) => void takeOver(w)} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 8, xl: 9 }} order={{ base: 1, md: 2 }}>{main}</Grid.Col>
        </Grid>
      ) : main}
    </Layout>
  )
}
