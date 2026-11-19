import { clock, dayClock } from '@/lib/time'

/** [unix seconds, value], oldest first: what the series APIs answer (telemetry, agent history). */
export type TimePoint = [number, number]

/** A line over time with a soft fill, broken where samples are missing (an agent away, a restart).
 *  Plain SVG like the other charts here, so any page or dashboard tile can use it. */
export function TimeChart({ points, label, since, until, format = String, height = 120 }: {
  points: TimePoint[]
  label: string
  /** The window drawn, so a short series sits where it happened instead of filling the width. */
  since: number
  until: number
  /** How the highest value is written under the chart ("max 1,317"). */
  format?: (v: number) => string
  height?: number
}) {
  const W = 600, H = height
  const top = Math.max(...points.map((p) => p[1]), 1)
  const x = (ts: number) => ((ts - since) / (until - since || 1)) * W
  const y = (v: number) => H - 2 - (v / top) * (H - 10)
  const runs = split(points)
  const when = until - since >= 86400 ? dayClock : clock
  return (
    <figure className="fb-time-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ height: H }}>
        <line className="axis" x1={0} x2={W} y1={H - 1} y2={H - 1} vectorEffect="non-scaling-stroke" />
        {runs.map((run, i) => {
          const line = run.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')
          return run.length > 1 ? (
            <g key={i}>
              <polygon className="area" points={`${x(run[0][0]).toFixed(1)},${H} ${line} ${x(run[run.length - 1][0]).toFixed(1)},${H}`} />
              <polyline className="line" points={line} vectorEffect="non-scaling-stroke" />
            </g>
          ) : <circle key={i} className="dot" cx={x(run[0][0])} cy={y(run[0][1])} r={2.5} />
        })}
      </svg>
      <figcaption>
        <span>{when(since)}</span>
        <span>{format(top)}</span>
        <span>{when(until)}</span>
      </figcaption>
    </figure>
  )
}

/** Runs of samples without a hole: a gap of three steps or more is drawn as nothing. */
function split(points: TimePoint[]): TimePoint[][] {
  if (points.length < 2) return points.length ? [points] : []
  const gaps = points.slice(1).map((p, i) => p[0] - points[i][0]).sort((a, b) => a - b)
  const step = gaps[Math.floor(gaps.length / 2)] || 60
  const out: TimePoint[][] = [[points[0]]]
  for (let i = 1; i < points.length; i++) {
    if (points[i][0] - points[i - 1][0] > step * 3) out.push([])
    out[out.length - 1].push(points[i])
  }
  return out
}
