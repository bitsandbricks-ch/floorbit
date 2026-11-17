import type { PowerMarkers, PowerState } from '@/api/types'

const WORSE: PowerState[] = ['unknown', 'ok', 'warn', 'crit', 'tripped']

/** Each board's busiest circuit and worst state, for the bar under its box on the power layer:
 *  one look says which board is close to its limit without hovering every cable. */
export function boardLoads(power: PowerMarkers): Map<string, { pct: number | null; state: PowerState; circuits: number; tripped: number }> {
  const out = new Map<string, { pct: number | null; state: PowerState; circuits: number; tripped: number }>()
  for (const c of power.circuits) {
    const was = out.get(c.board) ?? { pct: null, state: 'unknown' as PowerState, circuits: 0, tripped: 0 }
    out.set(c.board, {
      pct: c.pct == null ? was.pct : Math.max(was.pct ?? 0, c.pct),
      state: WORSE.indexOf(c.state) > WORSE.indexOf(was.state) ? c.state : was.state,
      circuits: was.circuits + 1,
      tripped: was.tripped + (c.state === 'tripped' ? 1 : 0),
    })
  }
  return out
}
