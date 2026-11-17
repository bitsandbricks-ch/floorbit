import { Text } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { FirewallSeats, IncidentMarkers, PowerMarkers, SeatViewData, WifiData } from '@/api/types'
import { PRESETS, type LayerState } from '../plan/layers'
import type { View } from '../plan/model'
import { SeatMap } from '../plan/SeatMap'
import { useCablePlan } from '../plan/cablePlan'
import { areaView, seatsIn, type Pane } from './model'

type PlanPaneDef = Extract<Pane, { kind: 'plan' }>

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
export function PlanPane({ pane, cycle }: { pane: PlanPaneDef; cycle?: number }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const hallList = useQuery({
    queryKey: qk.options('halls', ''), queryFn: () => get<{ options: { value: string }[] }>('/api/options/halls'),
    enabled: !!cycle && !pane.hall, staleTime: 60_000,
  }).data?.options.map((o) => ({ id: o.value }))
  const hall = useHall(pane, cycle, hallList)
  const q = useQuery({
    queryKey: qk.plan(hall),
    queryFn: () => get<SeatViewData>(`/api/plan${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`),
    refetchInterval: 30_000,
  })
  const data = q.data
  const refresh = useCallback(() => { void qc.invalidateQueries({ queryKey: qk.planAll }) }, [qc])
  useLiveEvent('stats.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('plan.changed', refresh)

  const layers: LayerState = useMemo(() => ({ on: new Set(PRESETS[pane.preset]), fade: {} }), [pane.preset])
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
  const cablePlan = useCablePlan(data?.hall, pane.preset === 'network')
  const cables = pane.preset === 'network' ? cablePlan : undefined

  const drawing = data?.drawing
  const home = useMemo(() => (drawing ? areaView(pane.area, drawing) : null), [drawing, pane.area])
  const [moved, setMoved] = useState<View | null>(null)
  // Someone zoomed in on the screen: back to the pane's area after a minute.
  useEffect(() => {
    if (!moved) return
    const timer = window.setTimeout(() => setMoved(null), 60_000)
    return () => window.clearTimeout(timer)
  }, [moved])
  const inArea = useMemo(() => (drawing && home ? new Set(seatsIn(drawing, home)) : null), [drawing, home])

  const hallName = data?.halls.find((h) => h.id === data.hall)?.name ?? ''
  const areaName = pane.area.kind === 'block' ? t('dashboards.area.blockName', { name: pane.area.id })
    : pane.area.kind === 'zone' ? drawing?.marks?.find((m) => m.id === (pane.area as { id: string }).id)?.label || t('dashboards.area.zone')
    : pane.area.kind === 'box' ? t('dashboards.area.box') : ''
  const title = pane.title || [hallName, areaName].filter(Boolean).join(' · ')
  const seats = data && inArea ? [...inArea].map((s) => data.seats[s]).filter(Boolean) : []
  const online = seats.filter((s) => s.state === 'online').length
  const problems = seats.filter((s) => s.problems).length

  let body: React.ReactNode
  if (q.isPending) body = null
  else if (q.error) body = <Text c="down" className="fb-pane-note">{t('dashboards.pane.failed')}</Text>
  else if (!drawing) body = <Text c="dimmed" className="fb-pane-note">{t('dashboards.pane.noPlan')}</Text>
  else if (!home) body = <Text c="dimmed" className="fb-pane-note">{t('dashboards.pane.areaGone')}</Text>
  else {
    body = (
      <SeatMap data={data} view={moved ?? home} setView={setMoved} filter={pane.show} selected={null} onSelect={() => {}}
        layers={layers} traffic={on('status')} power={power?.enabled ? power : undefined}
        firewalls={firewalls?.enabled ? firewalls.seats : undefined} wifi={wifi} incidents={incidents}
        cables={cables?.cables} labels={pane.labels} />
    )
  }
  return (
    <div className={`fb-pane fb-pane-plan${pane.hide_title ? ' fb-pane-nohead' : ''}`} role="region" aria-label={title}>
      {!pane.hide_title && <div className="fb-pane-head">
        <Text fw={800} className="fb-pane-title" truncate>{title}</Text>
        {data && inArea && (
          <Text className="fb-pane-count">
            <b>{online}</b> / {seats.length} {t('plan.online')}
            {problems > 0 && <Text span c="down" fw={700}> · {t('dashboards.pane.problems', { count: problems })}</Text>}
          </Text>
        )}
      </div>}
      <div className="fb-pane-body">{body}</div>
    </div>
  )
}
