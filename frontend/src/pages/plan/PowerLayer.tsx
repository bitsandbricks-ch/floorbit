import { useTranslation } from 'react-i18next'
import type { PlanDrawing, PowerMarkers } from '@/api/types'
import { seatCenter } from './model'
import { boardLoads } from './powerLoad'

/** The power layer (issue #468): each distribution board as a box, and a cable from it to what each
 *  circuit feeds (the middle of its seats, and its switches), coloured by the circuit's load. */
export function PowerLayer({ power, drawing, switches, size }: {
  power: PowerMarkers; drawing: PlanDrawing; switches: { id: string; x: number; y: number }[]; size: { w: number; h: number }
}) {
  const { t } = useTranslation()
  const boards = new Map(power.boards.map((b) => [b.id, { ...b, px: (b.x / 100) * size.w, py: (b.y / 100) * size.h }]))
  const at = new Map(switches.map((w) => [w.id, w]))
  const loads = boardLoads(power)
  const label = (name: string, state: string, pct: number | null) =>
    `${name}: ${state === 'tripped' ? t('plan.power.tripped') : pct == null ? t('plan.power.noReading') : `${pct} %`}`
  return (
    <g className="power-layer">
      {power.circuits.map((c) => {
        const board = boards.get(c.board)
        if (!board) return null
        const points = c.seats.map((s) => seatCenter(drawing, s)).filter((p): p is { x: number; y: number } => !!p)
        const ends = points.length ? [{ x: points.reduce((a, p) => a + p.x, 0) / points.length, y: points.reduce((a, p) => a + p.y, 0) / points.length }] : []
        for (const id of c.switches) {
          const w = at.get(id)
          if (w) ends.push({ x: w.x, y: w.y })
        }
        return ends.map((e, i) => (
          <line key={`${c.id}-${i}`} className={`pcable pw-${c.state}`} x1={board.px} y1={board.py} x2={e.x} y2={e.y} vectorEffect="non-scaling-stroke">
            <title>{label(c.name, c.state, c.pct)}</title>
          </line>
        ))
      })}
      {[...boards.values()].map((b) => {
        const load = loads.get(b.id)
        const pct = load?.pct == null ? null : Math.round(load.pct)
        return (
          <g key={b.id} className={`pboard pw-${b.state}`} transform={`translate(${b.px} ${b.py})`}>
            <rect x={-24} y={-15} width={48} height={30} rx={4} />
            <text y={5} fontSize={13} textAnchor="middle">{b.name.slice(0, 6)}</text>
            {/* The busiest circuit's load as a bar under the box, and in words when one tripped. */}
            {load && (load.tripped > 0 ? (
              <text className="pload-text pw-tripped" y={30} fontSize={11} textAnchor="middle">{t('plan.power.trippedCount', { count: load.tripped })}</text>
            ) : pct != null && (
              <g className={`pload pw-${load.state}`}>
                <rect className="pload-track" x={-24} y={19} width={48} height={5} rx={2.5} />
                <rect className="pload-fill" x={-24} y={19} width={(48 * Math.min(pct, 100)) / 100} height={5} rx={2.5} />
                <text className="pload-text" y={37} fontSize={11} textAnchor="middle">{`${pct} %`}</text>
              </g>
            ))}
            <title>{load ? t('plan.power.board', { name: b.name, count: load.circuits, pct: pct ?? '–' }) : b.name}</title>
          </g>
        )
      })}
    </g>
  )
}
