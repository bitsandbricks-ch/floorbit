import { Alert, Anchor, Button, Drawer, Group, Kbd, Menu, Paper, SegmentedControl, Select, Text, TextInput } from '@mantine/core'
import { useHotkeys, useMediaQuery } from '@mantine/hooks'
import { IconPhoto, IconPrinter, IconSearch } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { notifications } from '@mantine/notifications'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { FirewallSeats, IncidentMarkers, PlayerHit, PowerMarkers, SeatViewData, WifiData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { BlockPanel } from './plan/BlockPanel'
import { SwitchPanel } from './plan/SwitchPanel'
import { Inspector, Legend } from './plan/Inspector'
import { type LayerId, type LayerState, readLayers, writeLayers } from './plan/layers'
import { LayersPanel } from './plan/LayersPanel'
import { type Filter, type View, around, findSeat, matches, parseBox, seatCenter, widen } from './plan/model'
import { SeatList } from './plan/SeatList'
import { SeatMap } from './plan/SeatMap'
import { download, fileName, inlineImages, standaloneSvg, svgToPng } from './plan/exportImage'
import { Shortcuts } from './plan/Shortcuts'
import { StaleNotice } from './plan/StaleNotice'
import { Modes } from './plan/Modes'
import { useCablePlan } from './plan/cablePlan'
import { PlanEditor } from './plan/edit/PlanEditor'
import { MODE_LAYERS, readMode, switchMode } from './plan/workspace'
import { LoadingState, ErrorBanner } from '@/components/ui'

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
  // Which layers are drawn over the seats, and how strong (issue: floor plan layers). Old ?traffic=1 links still work.
  const paramText = params.toString()
  // A mode link without its own layers (``/plan?mode=network``) shows the mode's layers.
  const mode = readMode(params)
  const layers = useMemo(() => {
    const read = readLayers(params)
    return params.has('mode') && !params.has('layers') ? { ...read, on: new Set(MODE_LAYERS[mode]) } : read
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramText])
  const traffic = layers.on.has('status')
  const powerOn = layers.on.has('electrical')
  const firewallOn = layers.on.has('firewalls')
  const wifiOn = layers.on.has('wifi')
  const crewOn = layers.on.has('crew')
  const list = !screen && params.get('view') === 'list'
  // Big screens can rotate through the halls (issue #163): ?cycle=30 shows each for 30 seconds.
  const cycle = screen && params.get('cycle') ? Math.max(10, Number(params.get('cycle')) || 30) : 0
  const phone = useMediaQuery('(max-width: 48em)')
  const qc = useQueryClient()
  // A link with a seat or switch but no hall (from the incident board) opens the hall it is in (issue #206).
  // Only the first load asks by seat, so clicking around keeps the same hall.
  const [focus] = useState(() => {
    if (hall) return ''
    const seat = params.get('seat'), sw = params.get('switch')
    return seat ? `seat=${encodeURIComponent(seat)}` : sw ? `switch=${encodeURIComponent(sw)}` : ''
  })
  const q = useQuery({
    queryKey: qk.plan(hall || focus),
    queryFn: () => get<SeatViewData>(`/api/plan${hall ? `?hall=${encodeURIComponent(hall)}` : focus ? `?${focus}` : ''}`),
    refetchInterval: 30_000,
  })
  // Seat cables and patch panels: drawn in Network mode (and Edit mode, which asks on its own).
  const cablePlan = useCablePlan(q.data?.hall, mode === 'network' && layers.on.has('network') && !print)
  // The power layer (issue #468): asked once to know whether Electrics is on, then kept fresh while shown.
  const markers = useQuery({
    queryKey: qk.powerMarkers, queryFn: () => get<PowerMarkers>('/api/power/markers'),
    refetchInterval: powerOn ? 30_000 : false, staleTime: 60_000, enabled: !print,
  })
  const power = powerOn && markers.data?.enabled ? markers.data : undefined
  // The firewall layer (issue #470): offered once ranges are planned, kept fresh while shown.
  const fwSeats = useQuery({
    queryKey: qk.firewallSeats, queryFn: () => get<FirewallSeats>('/api/firewalls/seats'),
    refetchInterval: firewallOn ? 15_000 : false, staleTime: 60_000, enabled: !print && !screen,
  })
  const firewalls = firewallOn && fwSeats.data?.enabled ? fwSeats.data.seats : undefined
  // Wi-Fi access points of the hall shown; asked once to know whether there are any.
  const shownHall = q.data?.hall ?? ''
  const wifiQ = useQuery({
    queryKey: qk.wifi(shownHall), queryFn: () => get<WifiData>(`/api/wifi?hall=${encodeURIComponent(shownHall)}`),
    refetchInterval: wifiOn ? 30_000 : false, staleTime: 60_000, enabled: !print && !!shownHall, retry: false,
  })
  const wifiPlaced = !!wifiQ.data?.aps.some((a) => a.on_plan)
  const wifi = wifiOn && wifiPlaced ? wifiQ.data : undefined
  // Open incidents per seat for the crew layer; people without the incident board don't get the layer.
  const incidentQ = useQuery({
    queryKey: qk.incidentMarkers, queryFn: () => get<IncidentMarkers>('/api/incidents/markers'),
    refetchInterval: crewOn ? 30_000 : false, staleTime: 60_000, enabled: !print && !screen, retry: false,
  })
  const incidents = crewOn && incidentQ.data ? incidentQ.data : undefined
  const setLayers = (next: LayerState) => setParams(writeLayers(params, next), { replace: true })
  const refresh = useCallback(() => { void qc.invalidateQueries({ queryKey: qk.planAll }) }, [qc])
  useLiveEvent('stats.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('plan.changed', refresh)
  // With the power layer on, the view takes in the boards too: they usually hang on the walls.
  const data = useMemo(() => {
    let d = q.data
    // An empty hall has no drawing; Edit mode starts it from a blank sheet the plan's size.
    if (d && !d.drawing && mode === 'edit') d = { ...d, drawing: { shapes: [], marks: [], icons: {}, box: `0 0 ${d.size.w} ${d.size.h}`, cell: d.size.cell } }
    if (!d?.drawing || !power?.boards.length) return d
    const fed = new Set(power.circuits.flatMap((c) => c.switches))
    const at = [...power.boards.map((b) => ({ x: (b.x / 100) * d.size.w, y: (b.y / 100) * d.size.h })),
      ...d.switches.filter((w) => fed.has(w.id))]
    return { ...d, drawing: { ...d.drawing, box: widen(d.drawing.box, at) } }
  }, [q.data, power, mode])
  const [saved, setSaved] = useState<{ box: string; view: View } | null>(null)
  // The filter lives in the address so a reload or a shared link keeps it (issue #192).
  const filter: Filter = FILTERS.includes(params.get('show') as Filter) ? params.get('show') as Filter : 'all'
  const [search, setSearch] = useState('')
  // "/" jumps to the Find box, as on most sites with a search (issue #194). Mantine skips it while typing elsewhere.
  const findBox = useRef<HTMLInputElement>(null)
  const keyboard = useMediaQuery('(hover: hover) and (pointer: fine)')
  const toFind = () => { findBox.current?.focus(); findBox.current?.select() }
  // Swiss and German keyboards type "/" with Shift (Shift+7), and Mantine matches Shift exactly (issue #222).
  // "?" lists the shortcuts, as on GitHub and Gmail (issue #224). Usually typed with Shift.
  const [shortcuts, setShortcuts] = useState(false)
  const showShortcuts = () => setShortcuts(true)
  useHotkeys([['/', toFind], ['shift+/', toFind], ['shift+?', showShortcuts], ['?', showShortcuts]])
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
  const canEdit = useCan('floorplan.edit')
  const editing = mode === 'edit' && canEdit
  const [players, setPlayers] = useState<{ query: string; hits: PlayerHit[] } | null>(null)
  // Another hall in the same mode (Edit stays Edit) and with the same filter.
  const toHall = (id: string) => {
    const next = new URLSearchParams()
    next.set('hall', id)
    if (params.get('mode')) next.set('mode', params.get('mode')!)
    if (filter !== 'all') next.set('show', filter)
    setParams(next)
  }
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
  const counts = Object.fromEntries(FILTERS.map((f) => [f, data ? Object.values(data.seats).filter((x) => matches(x, f)).length : 0])) as Record<Filter, number>
  // Seats with problems in the halls not on screen (issue #196).
  const elsewhere = data ? data.halls.filter((h) => h.id !== data.hall).reduce((n, h) => n + (h.problems ?? 0), 0) : 0
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
    <SeatMap data={data} view={view} setView={setView} filter={filter} selected={selected} traffic={traffic} power={power} firewalls={firewalls}
      layers={layers} wifi={wifi} incidents={incidents} cables={cablePlan?.cables}
      onClear={() => set('seat', null)}
      onSelect={(s) => { if (!screen) set('seat', s === selected ? null : s) }}
      onBlock={screen ? undefined : (b) => set('block', b)} onSwitch={screen ? undefined : (w) => set('switch', w)} />
  )
  const summary = data && (
    <Group gap="lg" className="fb-plan-summary" wrap="wrap">
      <Text><b>{online}</b> / {total} {t('plan.online')}</Text>
      <Text c={problems ? 'down' : 'dimmed'}><b>{problems}</b> {t('plan.withProblems')}</Text>
      {data.last_read && <Text c="dimmed" size="sm">{t('plan.lastRead', { time: clock(data.last_read) })}</Text>}
      {!print && <StaleNotice updatedAt={q.dataUpdatedAt} failing={q.isRefetchError} />}
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
            <SaveImage hall={hallName ?? ''} />
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
        {data && <Legend checkin={data.checkin && layers.on.has('checkin')} traffic={traffic} power={!!power} />}
      </main>
    )
  }

  const inspector = selected
    ? <Inspector key={selected} seat={selected} onClose={() => set('seat', null)} onBlock={(b) => set('block', b)} />
    : blockSel ? <BlockPanel key={blockSel} name={blockSel} onSeat={(s) => set('seat', s)} onSwitch={(w) => set('switch', w)} onClose={() => set('block', null)} />
    : switchSel ? <SwitchPanel key={switchSel} name={switchSel} onSeat={(s) => set('seat', s)} onClose={() => set('switch', null)} /> : null
  const panel = !!inspector
  const available: Record<LayerId, boolean> = {
    grid: true, marks: true, network: true, safety: true, services: true, status: !!data?.monitoring, checkin: !!data?.checkin,
    electrical: !!markers.data?.enabled, firewalls: !!fwSeats.data?.enabled, wifi: wifiPlaced, crew: !!incidentQ.data,
  }
  return (
    <Layout title={t('plan.title')} back={{ href: '/', label: t('plan.editor') }} count={problems + elsewhere}>
      <PageHead title={t('plan.title')} />
      {q.isPending && <LoadingState />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {data && (
        <>
          <Group justify="space-between" mb="sm" gap="sm" wrap="wrap">
            <Group gap="lg" wrap="wrap">
              <Modes mode={mode} hall={data.hall} params={params} checkin={data.checkin} canEdit={canEdit}
                onMode={(m) => setParams(switchMode(params, m, layers), { replace: true })} />
              {summary}
            </Group>
            <Group gap="xs" wrap="wrap">
              {data.halls.length > 1 && (
                <Select aria-label={t('plan.hall')} w={180} comboboxProps={{ width: 'max-content', position: 'bottom-start' }}
                  allowDeselect={false} value={data.hall}
                  data={data.halls.map((h) => ({ value: h.id, label: h.name }))}
                  renderOption={({ option }) => <HallOption hall={data.halls.find((h) => h.id === option.value)!} />}
                  onChange={(v) => { if (v) toHall(v) }} />
              )}
              {elsewhere > 0 && <Text size="sm" c="down" fw={600}>{t('plan.elsewhere', { count: elsewhere })}</Text>}
              <Button variant="default" leftSection={<IconPrinter size={14} />} component="a"
                href={`/plan?print=1&hall=${encodeURIComponent(data.hall)}${filter !== 'all' ? `&show=${filter}` : ''}`}>{t('plan.print.print')}</Button>
              <form onSubmit={go} role="search">
                <TextInput ref={findBox} aria-label={t('plan.find')} aria-keyshortcuts="/" rightSection={keyboard ? <Kbd size="xs">/</Kbd> : undefined} placeholder={canPeople ? t('plan.findPlayerHint') : t('plan.findHint')} w={canPeople ? 200 : 160} value={search}
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
            {!editing && <>
            <SegmentedControl size="xs" value={filter} onChange={(v) => set('show', v === 'all' ? null : v)} aria-label={t('plan.show')}
              data={FILTERS.filter((f) => data.checkin || f !== 'checked_in').map((f) => ({
                value: f,
                // Each filter says how many seats it holds (issue #190), so the row doubles as a summary.
                label: <span><span>{t(`plan.filter.${f}`)}</span> <span className="fb-filter-count">{counts[f]}</span></span>,
              }))} />
            <SegmentedControl size="xs" value={list ? 'list' : 'map'} onChange={(v) => set('view', v === 'list' ? 'list' : null)}
              aria-label={t('plan.list.view')} data={[{ value: 'map', label: t('plan.list.map') }, { value: 'list', label: t('plan.list.list') }]} />
            </>}
            {!list && <LayersPanel state={layers} onChange={setLayers} available={available} />}
          </Group>
          {!data.drawing && (
            <Paper withBorder radius="lg" p="lg"><Text>{t('plan.empty')}</Text><Anchor href={`/plan?mode=edit&hall=${encodeURIComponent(data.hall)}`} mt="xs" display="inline-block">{t('plan.emptyLink')}</Anchor></Paper>
          )}
          {editing && data.drawing && view && (
            <PlanEditor data={data} view={view} setView={setView} layers={layers} refresh={() => qc.invalidateQueries({ queryKey: qk.planAll })} onHall={toHall} onShortcuts={showShortcuts} />
          )}
          {!editing && <div className={`fb-plan-layout${panel && !phone ? ' with-inspector' : ''}`}>
            {list ? <SeatList data={data} filter={filter} selected={selected} onSelect={(s) => set('seat', s === selected ? null : s)} /> : map}
            {panel && !phone && <Paper withBorder radius="lg" p="md">{inspector}</Paper>}
          </div>}
          {!list && !editing && <Legend checkin={data.checkin && layers.on.has('checkin')} traffic={traffic} power={!!power} firewalls={!!firewalls} />}
          {!list && !editing && (
            <Text size="sm" c="dimmed" mt="xs">
              {t('plan.help')}
              {keyboard && <>{' '}<Anchor component="button" type="button" size="sm" onClick={showShortcuts}>{t('plan.shortcuts.show')}</Anchor> <Kbd size="xs">?</Kbd></>}
            </Text>
          )}
          <Shortcuts opened={shortcuts} onClose={() => setShortcuts(false)} editing={editing} />
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

/** A hall in the picker with its totals, so trouble in another hall shows before switching to it. */
function HallOption({ hall }: { hall: SeatViewData['halls'][number] }) {
  const { t } = useTranslation()
  return (
    <div>
      <Text size="sm">{hall.name}</Text>
      <Text size="xs" c="dimmed">
        {t('plan.hallTotals', { online: hall.online, seats: hall.seats })}
        {hall.problems > 0 && <Text span size="xs" c="down" fw={600}> · {hall.problems} {t('plan.withProblems')}</Text>}
      </Text>
    </div>
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

/** Save the print sheet's plan as a picture, for a chat or a briefing slide: PNG (twice the screen's
 *  width, so it stays sharp when zoomed) or SVG (sharp at any size). */
function SaveImage({ hall }: { hall: string }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const save = async (as: 'png' | 'svg') => {
    const svg = document.querySelector<SVGSVGElement>('.fb-plan-print svg[role="application"]')
    if (!svg) return
    setBusy(true)
    try {
      const out = standaloneSvg(svg, Math.max(1600, svg.clientWidth * 2))
      const text = await inlineImages(out.text)
      const blob = as === 'svg' ? new Blob([text], { type: 'image/svg+xml' }) : await svgToPng(text, out.width, out.height)
      download(blob, fileName(hall, as))
    } catch {
      notifications.show({ color: 'down', message: t('plan.print.imageFailed') })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="default" leftSection={<IconPhoto size={16} />} loading={busy}>{t('plan.print.image')}</Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item onClick={() => void save('png')}>{t('plan.print.png')}</Menu.Item>
        <Menu.Item onClick={() => void save('svg')}>{t('plan.print.svg')}</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
