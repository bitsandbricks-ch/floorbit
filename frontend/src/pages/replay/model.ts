import type { ReplayData, ReplayIncident, SeatChange } from '@/api/types'

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
export function chartPath(data: Pick<ReplayData, 'samples'>, start: number, end: number, w: number, h: number): string {
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
