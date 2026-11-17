import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanCable, PlanLink, PlanPanel, PlanSeat } from '@/api/types'
import { cablePath } from './cablePlan'
import { cableSummary, uplinkSummary } from './cableLegend'
import { bundles, plugAt } from './cableRoute'

const SPEED_W: Record<number, number> = { 1: 1.6, 10: 2.4, 25: 2.8, 40: 3.2, 100: 3.6 }

/** The seat port's state on its cable: solid while the port is up, dashed when it is down, dotted
 *  when it isn't read (Mike: "port up solid, else dashed"). No seat states: drawn solid. */
function portLook(seats: Record<string, PlanSeat> | undefined, c: PlanCable) {
  const state = seats && c.ref.seat ? seats[c.ref.seat]?.state ?? 'unknown' : 'online'
  return state === 'online' ? '' : state === 'offline' ? ' down' : ' unread'
}

/** Seat cables (switch port, through its patch panel, to the seat) and the patch panels, on the
 *  Network layer. Uplinks and power have their own layers.
 *
 *  Seat cables: the bundles under them (where three or more share a run, one band with a count),
 *  then each cable. ``scale`` keeps the counts the same size on screen at every zoom. */
export function CableLines({ cables, size, scale = 1, seats }: {
  cables: PlanCable[]; size: { w: number; h: number }; scale?: number; seats?: Record<string, PlanSeat>
}) {
  const { t } = useTranslation()
  const runs = useMemo(() => bundles(cables, size), [cables, size])
  const r = 9 / (scale || 1)
  return (
    <g className="seat-cables">
      {runs.map((b, i) => (
        <line key={`b${i}`} className="cable-bundle" x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2}
          strokeWidth={Math.min(14, 4 + b.count / 2)} vectorEffect="non-scaling-stroke" />
      ))}
      {cables.filter((c) => c.kind === 'lan').map((c) => (
        <path key={c.key} className={`seatcable m-${c.media || 'copper'}${c.ref.cable ? '' : ' learned'}${portLook(seats, c)}`} d={cablePath(c.points, size, c.corners)}
          strokeWidth={SPEED_W[c.speed ?? 1] ?? 1.6} vectorEffect="non-scaling-stroke" fill="none">
          <title>{`${c.label ? `${c.label}: ` : ''}${c.ref.switch} ${c.ref.port}${c.via ? ` → ${c.via}` : ''} → ${c.ref.seat}${c.ref.cable ? '' : ` (${t('plan.net.learned')})`}`}</title>
        </path>
      ))}
      {/* One count per bundle line, on its fullest stretch, so it reads as "12 cables" at a glance. */}
      {runs.filter((b) => b.label && Math.hypot(b.x2 - b.x1, b.y2 - b.y1) > r * 3).map((b, i) => (
        <g key={`n${i}`} className="cable-count" transform={`translate(${(b.x1 + b.x2) / 2} ${(b.y1 + b.y2) / 2})`}>
          <circle r={r} />
          <text dy="0.35em" fontSize={r * 1.1}>{b.count}</text>
          <title>{t('plan.net.bundle', { count: b.count })}</title>
        </g>
      ))}
    </g>
  )
}

/** Where each seat cable plugs in: a dot on the seat's edge, drawn over the seats, so a cable
 *  visibly ends at its seat and not somewhere at the block. */
export function CablePlugs({ cables, size, cell, seats }: { cables: PlanCable[]; size: { w: number; h: number }; cell: number; seats?: Record<string, PlanSeat> }) {
  return (
    <g className="cable-plugs" aria-hidden="true">
      {cables.map((c) => {
        const at = plugAt(c, size, cell)
        return at ? <circle key={c.key} className={`plug m-${c.media || 'copper'}${c.ref.cable ? '' : ' learned'}${portLook(seats, c)}`} cx={at[0]} cy={at[1]} r={Math.max(2.5, cell * 0.09)} /> : null
      })}
    </g>
  )
}

export function PanelGlyphs({ panels, near }: { panels: PlanPanel[]; near: boolean }) {
  const { t } = useTranslation()
  return (
    <g className="patch-panels">
      {panels.map((p) => (
        <g key={p.name} className={`ppanel${p.used >= p.ports ? ' full' : ''}`} transform={`translate(${p.x} ${p.y})`}>
          <rect x={-18} y={-7} width={36} height={14} rx={2} />
          {Array.from({ length: 6 }, (_, i) => <rect key={i} className={`pp-port${i < Math.round((p.used / p.ports) * 6) ? ' lit' : ''}`} x={-15 + i * 5} y={-3} width={3.5} height={6} rx={0.6} />)}
          <title>{t('plan.net.panel', { name: p.name, used: p.used, ports: p.ports })}</title>
          {near && <text y={19} fontSize={10}>{p.name}</text>}
        </g>
      ))}
    </g>
  )
}

const MEDIA_COLOR: Record<string, string> = { copper: 'var(--mantine-color-blue-6)', fiber: 'var(--mantine-color-cyan-6)', dac: 'var(--mantine-color-violet-6)' }
const line = (stroke: string, width: number, dash?: string) => (
  <svg width={28} height={10} aria-hidden="true"><line x1={2} y1={5} x2={26} y2={5} stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeDasharray={dash} /></svg>
)

/** What the seat cables' colours, widths and dashes mean, for the cables on this plan only. */
export function CableLegend({ cables, links = [] }: { cables: PlanCable[]; links?: PlanLink[] }) {
  const { t } = useTranslation()
  const s = cableSummary(cables)
  const up = uplinkSummary(links)
  if (!s.total && !up.total) return null
  return (
    <ul className="fb-plan-legend fb-cable-legend" aria-label={t('plan.net.legend')}>
      {up.total > 0 && <li><b>{t('plan.net.uplinks', { count: up.total })}</b></li>}
      {up.down > 0 && <li className="fb-legend-down">{line('var(--color-down)', 3, '6 4')}{t('plan.net.uplinksDown', { count: up.down })}</li>}
      {up.slow > 0 && <li>{line('var(--mantine-color-orange-6)', 3)}{t('plan.net.uplinksSlow', { count: up.slow })}</li>}
      {s.total > 0 && <li><b>{t('plan.net.cables', { count: s.total })}</b></li>}
      {s.media.map((m) => <li key={m}>{line(MEDIA_COLOR[m], 3)}{t(`plan.net.media.${m}`)}</li>)}
      {s.speeds.length > 1 && s.speeds.map((v) => <li key={v}>{line('var(--color-muted)', SPEED_W[v] ?? 1.6)}{t('plan.net.speed', { gbps: v })}</li>)}
      {s.total > 0 && <li>{line('var(--color-muted)', 2)}{t('plan.net.portUp')}</li>}
      {s.total > 0 && <li>{line('var(--color-muted)', 2, '6 4')}{t('plan.net.portDown')}</li>}
      {s.total > 0 && <li>{line('var(--color-muted)', 2, '1 4')}{t('plan.net.portUnknown')}</li>}
      {s.learned > 0 && <li>{line('color-mix(in srgb, var(--color-muted) 45%, transparent)', 2)}{t('plan.net.learnedCount', { count: s.learned })}</li>}
    </ul>
  )
}
