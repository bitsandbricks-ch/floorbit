import { Text } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { FirewallSeats, IncidentMarkers, PowerMarkers, SeatViewData, WifiData } from '@/api/types'
import { PRESETS, type LayerState } from '../plan/layers'
import type { View } from '../plan/model'
import { SeatMap } from '../plan/SeatMap'
import { useCablePlan } from '../plan/cablePlan'
import { turnHelps, turnPlan, turnView } from '../plan/turn'
import { useSize } from '../plan/useSize'
import { ProblemList } from './ProblemList'
import { problemSeats } from './problemSeats'
import './PlanPane.css'
import { areaView, blockText, findBlock, findRow, PUBLIC_MARK_LAYERS, seatsIn, type Pane } from './model'
import { publicUrl, useScreen } from './screen'

type PlanPaneDef = Extract<Pane, { kind: 'plan' }>

// From this wide a pane lists its problem seats beside the plan, in a column this wide (PlanPane.css).
const LIST_FROM = 720
const LIST_W = 220

/** The halls a rotating pane goes through, and which one is up. */
function useHall(pane: PlanPaneDef, cycle: number | undefined, halls: { id: string }[] | undefined) {
  const rotate = !!cycle && !pane.hall && pane.area.kind === 'hall' && (halls?.length ?? 0) > 1
  const [i, setI] = useState(0)
  useEffect(() => {
    if (!rotate) return
    const timer = window.setInterval(() => setI((n) => n + 1), cycle! * 1000)
    return () => window.clearInterval(timer)
  }, [rotate, cycle])
  return rotate && halls ? halls[i % halls.length].id : pane.hall
}

/** One floor plan pane of a dashboard: a hall, the part of it to show, a layer preset. Read only;
 *  someone at the screen can still drag and zoom, and it goes back to its area after a minute. */
export function PlanPane({ pane: given, cycle }: { pane: PlanPaneDef; cycle?: number }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const screen = useScreen()
  const open = screen.publicId   // a public dashboard nobody signed in to: its own feed, no crew layers
  // The screen's ?hall= stands in for "the first hall" (old /kiosk?hall= and /screen links).
  const pane = !given.hall && screen.hall ? { ...given, hall: screen.hall } : given
  const hallList = useQuery({
    queryKey: qk.options('halls', ''), queryFn: () => get<{ options: { value: string }[] }>('/api/options/halls'),
    enabled: !!cycle && !pane.hall && !open, staleTime: 60_000,
  }).data?.options.map((o) => ({ id: o.value }))
  const publicHalls = useQuery({
    queryKey: [...qk.plan(''), 'public', open], queryFn: () => get<SeatViewData>(publicUrl(open!, '/plan')),
    enabled: !!cycle && !pane.hall && !!open, staleTime: 60_000,
  }).data?.halls
  const hall = useHall(pane, cycle, open ? publicHalls : hallList)
  const at = hall ? `?hall=${encodeURIComponent(hall)}` : ''
  const q = useQuery({
    queryKey: open ? [...qk.plan(hall), 'public', open] : qk.plan(hall),
    queryFn: () => get<SeatViewData>(open ? publicUrl(open, `/plan${at}`) : `/api/plan${at}`),
    refetchInterval: 30_000,
  })
  const marks = pane.marks ?? 'all'
  const data = useMemo(() => {
    const d = q.data
    if (!d?.drawing || marks === 'all') return d
    const kept = marks === 'none' ? [] : (d.drawing.marks ?? []).filter((m) => PUBLIC_MARK_LAYERS.includes(m.layer ?? 'overview'))
    return { ...d, drawing: { ...d.drawing, marks: kept } }
  }, [q.data, marks])
  const refresh = useCallback(() => { void qc.invalidateQueries({ queryKey: qk.planAll }) }, [qc])
  useLiveEvent('stats.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('plan.changed', refresh)

  const bodyRef = useRef<HTMLDivElement>(null)
  const px = useSize(bodyRef)
  const drawing = data?.drawing
  const home = useMemo(() => (drawing ? areaView(pane.area, drawing) : null), [drawing, pane.area])
  // The side list takes room from the plan: decide on turning for what is left.
  const wide = px.w >= LIST_FROM
  const room = { w: wide ? px.w - LIST_W : px.w, h: px.h }
  const turned = !!pane.turn && !!home && turnHelps(home, room)
  const shown = useMemo(() => (turned && data ? turnPlan(data) : data), [turned, data])

  const layers: LayerState = useMemo(() => {
    const on = new Set<string>(PRESETS[pane.preset])
    // Safety marks are public (exits, first aid): a public pane draws them whatever the preset.
    if (marks === 'public') on.add('safety')
    // Signed out there is no feed for power, firewalls, Wi-Fi, incidents or cables.
    if (open) for (const l of ['electrical', 'firewalls', 'wifi', 'crew']) on.delete(l)
    // Turned, these would draw where the hall was (they come in plan coordinates of their own).
    if (turned) for (const l of ['electrical', 'wifi']) on.delete(l)
    return { on: on as LayerState['on'], fade: {} }
  }, [pane.preset, marks, open, turned])
  const on = (id: string) => layers.on.has(id as never)
  // Cached answers from another pane come back even while a query is off: gate them on the layer too.
  const powerQ = useQuery({
    queryKey: qk.powerMarkers, queryFn: () => get<PowerMarkers>('/api/power/markers'),
    refetchInterval: 30_000, enabled: on('electrical'), retry: false,
  })
  const power = on('electrical') ? powerQ.data : undefined
  const firewallQ = useQuery({
    queryKey: qk.firewallSeats, queryFn: () => get<FirewallSeats>('/api/firewalls/seats'),
    refetchInterval: 15_000, enabled: on('firewalls'), retry: false,
  })
  const firewalls = on('firewalls') ? firewallQ.data : undefined
  const shownHall = data?.hall ?? ''
  const wifiQ = useQuery({
    queryKey: qk.wifi(shownHall), queryFn: () => get<WifiData>(`/api/wifi?hall=${encodeURIComponent(shownHall)}`),
    refetchInterval: 30_000, enabled: on('wifi') && !!shownHall, retry: false,
  })
  const wifi = on('wifi') ? wifiQ.data : undefined
  const incidentQ = useQuery({
    queryKey: qk.incidentMarkers, queryFn: () => get<IncidentMarkers>('/api/incidents/markers'),
    refetchInterval: 30_000, enabled: on('crew'), retry: false,
  })
  const incidents = on('crew') ? incidentQ.data : undefined
  const cablePlan = useCablePlan(data?.hall, pane.preset === 'network' && !open && !turned)
  const cables = pane.preset === 'network' && !open && !turned ? cablePlan : undefined
  // Where someone dragged the plan to, in the turned or the upright plan's coordinates.
  const [movedTo, setMovedTo] = useState<{ view: View; turned: boolean } | null>(null)
  const moved = movedTo && movedTo.turned === turned ? movedTo.view : null
  const setMoved = useCallback((view: View) => setMovedTo({ view, turned }), [turned])
  // Someone zoomed in on the screen: back to the pane's area after a minute.
  useEffect(() => {
    if (!moved) return
    const timer = window.setTimeout(() => setMovedTo(null), 60_000)
    return () => window.clearTimeout(timer)
  }, [moved])
  // A row's box reaches into the rows beside it: count only the row's own seats.
  const row = pane.area.kind === 'row' && drawing ? findRow(drawing, pane.area.id) : undefined
  const inArea = useMemo(() => (row ? new Set(row.cells.map((c) => c.seat))
    : drawing && home ? new Set(seatsIn(drawing, home)) : null), [row, drawing, home])

  const hallName = data?.halls.find((h) => h.id === data.hall)?.name ?? ''
  const block = pane.area.kind === 'block' && drawing ? findBlock(drawing, pane.area.id) : undefined
  const areaName = pane.area.kind === 'block' ? t('dashboards.area.blockName', { name: block ? blockText(t, block) : pane.area.id })
    : pane.area.kind === 'zone' ? drawing?.marks?.find((m) => m.id === (pane.area as { id: string }).id)?.label || t('dashboards.area.zone')
    : pane.area.kind === 'row' ? t('dashboards.area.rowName', { name: row ? row.name : pane.area.id })
    : pane.area.kind === 'box' ? t('dashboards.area.box') : ''
  const title = pane.title || [hallName, areaName].filter(Boolean).join(' · ')
  const seats = data && inArea ? [...inArea].map((s) => data.seats[s]).filter(Boolean) : []
  const online = seats.filter((s) => s.state === 'online').length
  const problems = seats.filter((s) => s.problems).length
  const listed = useMemo(() => (data && inArea ? problemSeats(data.seats, inArea) : []), [data, inArea])

  let body: React.ReactNode
  if (q.isPending) body = null
  else if (q.error && !data) body = <Text c="down" className="fb-pane-note">{t('dashboards.pane.failed')}</Text>
  else if (!drawing) body = <Text c="dimmed" className="fb-pane-note">{t('dashboards.pane.noPlan')}</Text>
  else if (!home) body = <Text c="dimmed" className="fb-pane-note">{t('dashboards.pane.areaGone')}</Text>
  else {
    const view = moved ?? (turned ? turnView(home) : home)
    body = (
      <SeatMap data={shown!} view={view} setView={setMoved} rings filter={pane.show} selected={null} onSelect={() => {}}
        layers={layers} traffic={on('status')} power={power?.enabled ? power : undefined}
        firewalls={firewalls?.enabled ? firewalls.seats : undefined} wifi={wifi} incidents={incidents}
        cables={cables?.cables} labels={pane.labels} focus={row && inArea ? { seats: inArea } : undefined} />
    )
  }
  return (
    <div className={`fb-pane fb-pane-plan${pane.hide_title ? ' fb-pane-nohead' : ''}`} role="region" aria-label={title}>
      {!pane.hide_title && <div className="fb-pane-head">
        <Text fw={600} className="fb-pane-title" truncate>{title}</Text>
        {data && inArea && (
          <Text className="fb-pane-count">
            <b>{online}</b> / {seats.length} {t('plan.online')}
            {problems > 0 && <Text span c="down" fw={700}> · {t('dashboards.pane.problems', { count: problems })}</Text>}
          </Text>
        )}
      </div>}
      <div ref={bodyRef} className={`fb-pane-body${wide && listed.length ? ' fb-plan-listed' : ''}`}>
        {body}
        {wide && listed.length > 0 && drawing && home && <ProblemList seats={listed} />}
      </div>
    </div>
  )
}
