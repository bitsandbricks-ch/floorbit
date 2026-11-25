import { useQuery } from '@tanstack/react-query'
import { Group, Text } from '@mantine/core'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EventFrame, PlanDrawing, SeatViewData } from '@/api/types'
import { MiniPlan } from '@/components/MiniPlan'
import { contentBox } from '../dashboards/model'
import type { LayerState } from '../plan/layers'
import type { View } from '../plan/model'
import { SeatMap } from '../plan/SeatMap'
import { chartPath } from './model'

export const CHART_W = 1000
export const CHART_H = 120

// Walls, zones and the switches' places; seat states come from the frame, not from now.
const LAYERS: LayerState = { on: new Set(['marks', 'network', 'crew']), fade: {} }

/** The hall as the floor plan draws it (#1055), with each seat as the recording had it at that
 *  moment: online or not, and open incidents. Switches are drawn without a state: the recording
 *  keeps none. Without the live plan (an older server, no access) the small plan stands in. */
export function Plan({ hall, drawing, frame, label }: {
  hall: string; drawing: PlanDrawing; frame: EventFrame | null; label: string
}) {
  const { t } = useTranslation()
  const live = useQuery({
    queryKey: qk.plan(hall), queryFn: () => get<SeatViewData>(`/api/plan?hall=${encodeURIComponent(hall)}`),
    staleTime: 60_000,
  }).data
  const on = useMemo(() => new Set(frame?.seats ?? []), [frame])
  const rings = useMemo(() => new Set(frame?.incidents ?? []), [frame])
  const shown = useMemo<SeatViewData | null>(() => {
    if (!live?.drawing) return null
    const ids = live.drawing.shapes.flatMap((b) => b.cells.map((c) => c.seat))
    return {
      ...live,
      seats: Object.fromEntries(ids.map((id) => [id, { state: on.has(id) ? 'online' : 'offline' }])),
      switches: live.switches.map((s) => ({ ...s, status: 'unknown' })),
      blocks: live.blocks.map((b) => {
        const then = frame?.blocks[b.name.toUpperCase()]
        return { ...b, seats: then?.[0] ?? b.seats, online: then?.[1] ?? 0, problems: then?.[3] ?? 0 }
      }),
      links: [],
    }
  }, [live, on, frame])
  const drawn = live?.drawing
  const home = useMemo(() => (drawn ? contentBox(drawn) : null), [drawn])
  const [moved, setMoved] = useState<View | null>(null)
  const incidents = useMemo(() => ({ seats: Object.fromEntries([...rings].map((s) => [s, 1])), switches: {} }), [rings])

  if (shown && home) {
    return (
      <section className="fb-replay-map" aria-label={label}>
        <SeatMap data={shown} view={moved ?? home} setView={setMoved} filter="all" selected={null} onSelect={() => {}}
          layers={LAYERS} incidents={incidents} rings />
      </section>
    )
  }
  return (
    <>
      <MiniPlan drawing={drawing} label={label} className="fb-replay-plan" frames
        seat={(id, at) => ({
          className: on.has(id) ? 'on' : undefined,
          children: rings.has(id) ? <circle className="ring" cx={at.x} cy={at.y} r={drawing.cell * 0.9} /> : undefined,
        })} />
      <Group gap="md" mt="xs">
        <Text size="xs" c="dimmed"><span className="fb-replay-key on" /> {t('replay.online')}</Text>
        <Text size="xs" c="dimmed"><span className="fb-replay-key ring" /> {t('replay.openIncident')}</Text>
      </Group>
    </>
  )
}

/** Bandwidth over time, with the peak and a cursor; a click jumps there. */
export function Chart({ samples, peak, start, end, t, onSeek, label }: {
  samples: { t: number; down: number; up: number }[]; peak: { at: number } | null
  start: number; end: number; t: number; onSeek: (t: number) => void; label: string
}) {
  const span = Math.max(1, end - start)
  const x = (ts: number) => ((ts - start) / span) * CHART_W
  const line = chartPath({ samples }, start, end, CHART_W, CHART_H)
  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} preserveAspectRatio="none" className="fb-replay-chart" role="img" aria-label={label}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect()
        onSeek(start + ((e.clientX - box.left) / box.width) * span)
      }}>
      {line && <path d={`${line} L${CHART_W},${CHART_H} L0,${CHART_H} Z`} className="area" />}
      {line && <path d={line} className="line" />}
      {peak && peak.at >= start && <line className="peak" x1={x(peak.at)} x2={x(peak.at)} y1={0} y2={CHART_H} />}
      <line className="cursor" x1={x(t)} x2={x(t)} y1={0} y2={CHART_H} />
    </svg>
  )
}
