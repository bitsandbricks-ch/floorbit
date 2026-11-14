import { Alert, Anchor, Button, Drawer, Group, Loader, Paper, SegmentedControl, Select, Switch, Text, TextInput } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconPrinter, IconSearch } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { PlayerHit, SeatViewData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { BlockPanel } from './plan/BlockPanel'
import { SwitchPanel } from './plan/SwitchPanel'
import { Inspector, Legend } from './plan/Inspector'
import { type Filter, type View, around, findSeat, parseBox, seatCenter } from './plan/model'
import { SeatList } from './plan/SeatList'
import { SeatMap } from './plan/SeatMap'

const PANELS = ['seat', 'block', 'switch']
const FILTERS: Filter[] = ['all', 'problems', 'offline', 'recent', 'match', 'note', 'checked_in']

/** The floor plan's seats (issue #55): one state per seat that reads the same in every theme and
 *  for colour-blind eyes, three zoom levels, and one inspector for a seat. ``?screen=1`` for a kiosk. */
export default function FloorPlan() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const hall = params.get('hall') ?? ''
  const selected = params.get('seat')
  const blockSel = selected ? null : params.get('block')
  const switchSel = selected || blockSel ? null : params.get('switch')
  const screen = params.get('screen') === '1'
  // A sheet to print (issue #188): the whole hall, every seat numbered, light on white.
  const print = !screen && params.get('print') === '1'
  const traffic = params.get('traffic') === '1'
  const list = !screen && params.get('view') === 'list'
  // Big screens can rotate through the halls (issue #163): ?cycle=30 shows each for 30 seconds.
  const cycle = screen && params.get('cycle') ? Math.max(10, Number(params.get('cycle')) || 30) : 0
  const phone = useMediaQuery('(max-width: 48em)')
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: qk.plan(hall),
    queryFn: () => get<SeatViewData>(`/api/plan${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`),
    refetchInterval: 30_000,
  })
  const refresh = useCallback(() => { void qc.invalidateQueries({ queryKey: qk.planAll }) }, [qc])
  useLiveEvent('stats.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('plan.changed', refresh)
  const data = q.data
  const [saved, setSaved] = useState<{ box: string; view: View } | null>(null)
  const [filter, setFilter] = useState<Filter>(() => (FILTERS.includes(params.get('show') as Filter) ? params.get('show') as Filter : 'all'))
  const [search, setSearch] = useState('')
  const box = data?.drawing?.box
  // A new hall (or a changed drawing) starts fitted, or on the seat in the link it was opened with.
  const [linked] = useState(selected)
  const start = (() => {
    if (!box || !data?.drawing) return null
    const fit = parseBox(box)
    const at = linked ? seatCenter(data.drawing, linked) : null
    return at ? around(at, Math.max(fit.w / 2, 480), fit) : fit
  })()
  const view = saved && saved.box === box ? saved.view : start
  const setView = useCallback((v: View) => { if (box) setSaved({ box, view: v }) }, [box])

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    // One panel at a time: a seat, a block or a switch.
    if (value && PANELS.includes(key)) PANELS.filter((k) => k !== key).forEach((k) => next.delete(k))
    setParams(next, { replace: true })
  }
  // With seats.view the search also finds players by nick, IP or MAC (issue #186).
  const canPeople = useCan('seats.view')
  const [players, setPlayers] = useState<{ query: string; hits: PlayerHit[] } | null>(null)
  const jump = (seat: string, hall?: string) => {
    setPlayers(null)
    if (hall && data && hall !== data.hall) {
      const next = new URLSearchParams(params)
      next.set('hall', hall)
      next.set('seat', seat)
      PANELS.filter((k) => k !== 'seat').forEach((k) => next.delete(k))
      setParams(next)
      return
    }
    const at = data?.drawing && seatCenter(data.drawing, seat)
    if (!at || !view || !data?.drawing) return
    set('seat', seat)
    setView(around(at, Math.max(parseBox(data.drawing.box).w / 2, 480), view))
  }
  const go = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!data?.drawing || !view) return
    const seat = findSeat(search, data.seats)
    if (seat) return jump(seat)
    if (!canPeople || search.trim().length < 2) return
    const q = search.trim()
    const found = await get<{ results: PlayerHit[] }>(`/api/plan/find?q=${encodeURIComponent(q)}`).catch(() => ({ results: [] }))
    if (found.results.length === 1) return jump(found.results[0].seat, found.results[0].hall)
    setPlayers({ query: q, hits: found.results })
  }
  const searched = players && players.query === search.trim()
  const notFound = search.trim() !== '' && data && !findSeat(search, data.seats)
    ? (canPeople ? !!searched && players.hits.length === 0 : true) : false
  const total = data ? Object.keys(data.seats).length : 0
  const online = data ? Object.values(data.seats).filter((s) => s.state === 'online').length : 0
  const problems = data ? Object.values(data.seats).filter((s) => s.problems).length : 0
  const halls = data?.halls
  const rotating = cycle > 0 && (halls?.length ?? 0) > 1
  // A hall with problems stays up twice as long: that's the one the crew needs to look at.
  const dwell = rotating ? cycle * 1000 * (problems ? 2 : 1) : 0
  const current = data?.hall
  useEffect(() => {
    if (!dwell || !current || !halls) return
    const timer = window.setTimeout(() => {
      const i = halls.findIndex((h) => h.id === current)
      const next = new URLSearchParams(params)
      next.set('hall', halls[(i + 1) % halls.length].id)
      setParams(next, { replace: true })
    }, dwell)
    return () => window.clearTimeout(timer)
  }, [dwell, current, halls, params, setParams])
  const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })

  const map = data?.drawing && view && (
    <SeatMap data={data} view={view} setView={setView} filter={filter} selected={selected} traffic={traffic}
      onClear={() => set('seat', null)}
      onSelect={(s) => { if (!screen) set('seat', s === selected ? null : s) }}
      onBlock={screen ? undefined : (b) => set('block', b)} onSwitch={screen ? undefined : (w) => set('switch', w)} />
  )
  const summary = data && (
    <Group gap="lg" className="fb-plan-summary" wrap="wrap">
      <Text><b>{online}</b> / {total} {t('plan.online')}</Text>
      <Text c={problems ? 'down' : 'dimmed'}><b>{problems}</b> {t('plan.withProblems')}</Text>
      {data.last_read && <Text c="dimmed" size="sm">{t('plan.lastRead', { time: clock(data.last_read) })}</Text>}
    </Group>
  )

  if (print) {
    const hallName = data?.halls.find((h) => h.id === data.hall)?.name
    return (
      <main className="fb-plan-print">
        <PrintTheme />
        <Group justify="space-between" align="flex-end" mb="xs">
          <div>
            <Text fw={800} size="xl">{t('plan.print.title', { hall: hallName ?? '' })}</Text>
            {summary}
            {filter !== 'all' && <Text size="sm">{t('plan.print.only', { filter: t(`plan.filter.${filter}`) })}</Text>}
          </div>
          <Group gap="xs" className="fb-no-print">
            <Button variant="default" component="a" href={`/plan${data ? `?hall=${encodeURIComponent(data.hall)}` : ''}`}>{t('plan.print.back')}</Button>
            <Button leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>{t('plan.print.print')}</Button>
          </Group>
        </Group>
        {data?.drawing && view && (
          <SeatMap data={data} view={view} setView={() => {}} filter={filter} selected={null} level="near" onSelect={() => {}} />
        )}
        {data && <Legend checkin={data.checkin} />}
      </main>
    )
  }

  if (screen) {
    return (
      <main className="fb-plan-screen">
        <div>
          {rotating && <Text className="fb-plan-hall" fw={800}>{halls?.find((h) => h.id === current)?.name}</Text>}
          {summary}
          {rotating && <div key={current} className="fb-plan-cycle" role="presentation" style={{ animationDuration: `${dwell}ms` }} />}
        </div>
        {map}
        {data && <Legend checkin={data.checkin} traffic={traffic} />}
      </main>
    )
  }

  const inspector = selected
    ? <Inspector key={selected} seat={selected} onClose={() => set('seat', null)} onBlock={(b) => set('block', b)} />
    : blockSel ? <BlockPanel key={blockSel} name={blockSel} onSeat={(s) => set('seat', s)} onSwitch={(w) => set('switch', w)} onClose={() => set('block', null)} />
    : switchSel ? <SwitchPanel key={switchSel} name={switchSel} onSeat={(s) => set('seat', s)} onClose={() => set('switch', null)} /> : null
  const panel = !!inspector
  return (
    <Layout title={t('plan.title')} back={{ href: '/', label: t('plan.editor') }}>
      {q.isPending && <Loader aria-label={t('common.loading')} />}
      {q.error && <Alert color="down" role="alert">{t('common.error', { message: q.error.message })}</Alert>}
      {data && (
        <>
          <Group justify="space-between" mb="sm" gap="sm" wrap="wrap">
            {summary}
            <Group gap="xs" wrap="wrap">
              {data.halls.length > 1 && (
                <Select aria-label={t('plan.hall')} w={180} allowDeselect={false} value={data.hall}
                  data={data.halls.map((h) => ({ value: h.id, label: h.name }))}
                  onChange={(v) => { const next = new URLSearchParams(); if (v) next.set('hall', v); setParams(next) }} />
              )}
              <Button variant="default" leftSection={<IconPrinter size={14} />} component="a"
                href={`/plan?print=1&hall=${encodeURIComponent(data.hall)}${filter !== 'all' ? `&show=${filter}` : ''}`}>{t('plan.print.print')}</Button>
              <form onSubmit={go} role="search">
                <TextInput aria-label={t('plan.find')} placeholder={canPeople ? t('plan.findPlayerHint') : t('plan.findHint')} w={canPeople ? 200 : 160} value={search}
                  leftSection={<IconSearch size={14} />} error={notFound ? t(canPeople ? 'plan.notFoundPlayer' : 'plan.notFound') : undefined}
                  onChange={(e) => setSearch(e.currentTarget.value)} />
              </form>
            </Group>
          </Group>
          {searched && players.hits.length > 1 && (
            <Group gap={6} mb="sm" justify="flex-end" role="list" aria-label={t('plan.players')}>
              {players.hits.map((h) => (
                <div key={h.seat} role="listitem">
                  <Button size="compact-sm" variant="default" onClick={() => jump(h.seat, h.hall)}>
                    {h.nick ? `${h.nick} · ${h.seat}` : h.seat}
                  </Button>
                </div>
              ))}
            </Group>
          )}
          {!data.monitoring && <Alert color="warn" mb="sm">{t('plan.noMonitoring')}</Alert>}
          <Group mb="sm" gap="lg" wrap="wrap">
            <SegmentedControl size="xs" value={filter} onChange={(v) => setFilter(v as Filter)} aria-label={t('plan.show')}
              data={FILTERS.filter((f) => data.checkin || f !== 'checked_in').map((f) => ({ value: f, label: t(`plan.filter.${f}`) }))} />
            <SegmentedControl size="xs" value={list ? 'list' : 'map'} onChange={(v) => set('view', v === 'list' ? 'list' : null)}
              aria-label={t('plan.list.view')} data={[{ value: 'map', label: t('plan.list.map') }, { value: 'list', label: t('plan.list.list') }]} />
            {!list && <Switch size="sm" label={t('plan.traffic')} checked={traffic} onChange={(e) => set('traffic', e.currentTarget.checked ? '1' : null)} />}
          </Group>
          {!data.drawing && (
            <Paper withBorder radius="lg" p="lg"><Text>{t('plan.empty')}</Text><Anchor href="/" mt="xs" display="inline-block">{t('plan.emptyLink')}</Anchor></Paper>
          )}
          <div className={`fb-plan-layout${panel && !phone ? ' with-inspector' : ''}`}>
            {list ? <SeatList data={data} filter={filter} selected={selected} onSelect={(s) => set('seat', s === selected ? null : s)} /> : map}
            {panel && !phone && <Paper withBorder radius="lg" p="md">{inspector}</Paper>}
          </div>
          {!list && <Legend checkin={data.checkin} traffic={traffic} />}
          {!list && <Text size="sm" c="dimmed" mt="xs">{t('plan.help')}</Text>}
          {phone && (
            <Drawer opened={panel} onClose={() => set(selected ? 'seat' : blockSel ? 'block' : 'switch', null)} position="bottom" size="55%" withCloseButton={false}
              title={null} aria-label={selected ?? blockSel ?? switchSel ?? ''}>
              {inspector}
            </Drawer>
          )}
        </>
      )}
    </Layout>
  )
}

/** Light colours while the print sheet is open, whatever the theme: toner, not ink. */
function PrintTheme() {
  useEffect(() => {
    const root = document.documentElement
    const before = root.dataset.theme
    root.dataset.theme = 'light'
    return () => { if (before === undefined) delete root.dataset.theme; else root.dataset.theme = before }
  }, [])
  return null
}
