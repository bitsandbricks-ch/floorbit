import { useTranslation } from 'react-i18next'
import type { PlanCable, PlanPanel } from '@/api/types'
import { cablePath } from './cablePlan'
import { cableSummary } from './cableLegend'

const SPEED_W: Record<number, number> = { 1: 1.6, 10: 2.4, 25: 2.8, 40: 3.2, 100: 3.6 }

/** Seat cables (switch port, through its patch panel, to the seat) and the patch panels, on the
 *  Network layer. Uplinks and power have their own layers. */
export function CableLines({ cables, size }: { cables: PlanCable[]; size: { w: number; h: number } }) {
  const { t } = useTranslation()
  return (
    <g className="seat-cables">
      {cables.filter((c) => c.kind === 'lan').map((c) => (
        <path key={c.key} className={`seatcable m-${c.media || 'copper'}${c.ref.cable ? '' : ' learned'}`} d={cablePath(c.points, size, c.corners)}
          strokeWidth={SPEED_W[c.speed ?? 1] ?? 1.6} vectorEffect="non-scaling-stroke" fill="none">
          <title>{`${c.label ? `${c.label}: ` : ''}${c.ref.switch} ${c.ref.port}${c.via ? ` → ${c.via}` : ''} → ${c.ref.seat}${c.ref.cable ? '' : ` (${t('plan.net.learned')})`}`}</title>
        </path>
      ))}
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
export function CableLegend({ cables }: { cables: PlanCable[] }) {
  const { t } = useTranslation()
  const s = cableSummary(cables)
  if (!s.total) return null
  return (
    <ul className="fb-plan-legend fb-cable-legend" aria-label={t('plan.net.legend')}>
      <li><b>{t('plan.net.cables', { count: s.total })}</b></li>
      {s.media.map((m) => <li key={m}>{line(MEDIA_COLOR[m], 3)}{t(`plan.net.media.${m}`)}</li>)}
      {s.speeds.length > 1 && s.speeds.map((v) => <li key={v}>{line('var(--color-muted)', SPEED_W[v] ?? 1.6)}{t('plan.net.speed', { gbps: v })}</li>)}
      {s.learned > 0 && <li>{line('var(--color-muted)', 2, '4 3')}{t('plan.net.learnedCount', { count: s.learned })}</li>}
    </ul>
  )
}
