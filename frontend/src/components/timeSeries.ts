import type { TimePoint } from '@bitsandbricks/widgets'

/** The sample nearest to ``ts``; points are oldest first. */
export function nearest(points: TimePoint[], ts: number): TimePoint | null {
  let best: TimePoint | null = null
  for (const p of points) if (!best || Math.abs(p[0] - ts) < Math.abs(best[0] - ts)) best = p
  return best
}

/** Lowest, average and highest of a series, for the line under a chart. */
export function stats(points: TimePoint[]) {
  const vs = points.map((p) => p[1])
  return { min: Math.min(...vs), max: Math.max(...vs), avg: vs.reduce((a, b) => a + b, 0) / (vs.length || 1) }
}
