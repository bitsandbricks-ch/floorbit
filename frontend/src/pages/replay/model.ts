import type { EventFrame, ReplayIncident, SeatChange } from '@/api/types'

/** The seats that were on at time t: the starting state, then every change up to t. */
export function seatsAt(base: string[], changes: SeatChange[], t: number): Set<string> {
  const on = new Set(base)
  for (const [at, seat, state] of changes) {
    if (at > t) break
    if (state) on.add(seat)
    else on.delete(seat)
  }
  return on
}

/** The last sample at or before t (the first one before the samples start). */
export function sampleAt<S extends { t: number }>(samples: S[], t: number): S | null {
  if (!samples.length) return null
  let lo = 0
  let hi = samples.length - 1
  if (t < samples[0].t) return samples[0]
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (samples[mid].t <= t) lo = mid
    else hi = mid - 1
  }
  return samples[lo]
}

export function openAt(incidents: ReplayIncident[], t: number): ReplayIncident[] {
  return incidents.filter((i) => i.start <= t && (i.end === null || i.end > t))
}

/** A path for the bandwidth chart, w by h, time on x and down+up on y. */
export function chartPath(data: { samples: { t: number; down: number; up: number }[] }, start: number, end: number, w: number, h: number): string {
  const max = Math.max(1, ...data.samples.map((s) => s.down + s.up))
  const span = Math.max(1, end - start)
  return data.samples
    .map((s, i) => `${i ? 'L' : 'M'}${(((s.t - start) / span) * w).toFixed(1)},${(h - ((s.down + s.up) / max) * h).toFixed(1)}`)
    .join(' ')
}

export const SPEEDS = [60, 300, 900, 3600] as const

export function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
}

export type HeatMetric = 'online' | 'traffic' | 'incidents'

export interface HeatColumn { t: number; end: number; values: number[]; raw: number[] }

/**
 * The block-by-time heatmap: one row per block, at most ``maxCols`` columns (frames are merged
 * when there are more). ``values`` are 0..1 for the colour: the share of seats online, the traffic
 * against the busiest block's peak, open incidents against the most there ever were in one block.
 */
export function heatmap(frames: EventFrame[], metric: HeatMetric, maxCols = 96): { names: string[]; cols: HeatColumn[] } {
  const names = [...new Set(frames.flatMap((f) => Object.keys(f.blocks)))].sort()
  const per = Math.max(1, Math.ceil(frames.length / maxCols))
  const cols: HeatColumn[] = []
  for (let i = 0; i < frames.length; i += per) {
    const group = frames.slice(i, i + per)
    const raw = names.map((n) => {
      const vals = group.map((f) => {
        const b = f.blocks[n]
        if (!b) return 0
        if (metric === 'online') return b[0] ? b[1] / b[0] : 0
        return metric === 'traffic' ? b[2] : b[3]
      })
      return metric === 'incidents' ? Math.max(...vals) : vals.reduce((a, v) => a + v, 0) / vals.length
    })
    cols.push({ t: group[0].t, end: group[group.length - 1].t, values: raw, raw })
  }
  const top = metric === 'online' ? 1 : Math.max(0, ...cols.flatMap((c) => c.raw))
  for (const c of cols) c.values = c.raw.map((v) => (top ? Math.min(1, v / top) : 0))
  return { names, cols }
}
