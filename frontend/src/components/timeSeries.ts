import type { TimePoint } from '@bitsandbricks/widgets'

/** Lowest, average and highest of a series, for the line under a chart. */
export function stats(points: TimePoint[]) {
  const vs = points.map((p) => p[1])
  return { min: Math.min(...vs), max: Math.max(...vs), avg: vs.reduce((a, b) => a + b, 0) / (vs.length || 1) }
}
