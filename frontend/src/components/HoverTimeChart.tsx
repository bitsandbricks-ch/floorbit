import { TimeChart, type TimePoint } from '@bitsandbricks/widgets'
import { useState, type KeyboardEvent, type MouseEvent } from 'react'
import { clock, dateTime } from '@/lib/time'
import { nearest } from './timeSeries'
import './HoverTimeChart.css'

/** The shared TimeChart with what it lacks (issue #868): hovering shows the time and value of the
 *  nearest sample with a marker, and the arrow keys walk the samples. */
export function HoverTimeChart({ points, label, since, until, format, value, height = 120 }: {
  points: TimePoint[]; label: string; since: number; until: number
  /** Under the chart: how its highest value is written. */
  format?: (v: number) => string
  /** In the hover note: how one value is written. */
  value: (v: number) => string
  height?: number
}) {
  const [at, setAt] = useState<number | null>(null)
  const span = until - since || 1
  const hit = at === null ? null : points[at] ?? null
  const move = (e: MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const ts = since + ((e.clientX - box.left) / (box.width || 1)) * span
    const p = nearest(points, ts)
    setAt(p ? points.indexOf(p) : null)
  }
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const last = points.length - 1
    setAt((i) => Math.max(0, Math.min(last, (i ?? last + 1) + (e.key === 'ArrowLeft' ? -1 : 1))))
  }
  const left = hit ? `${Math.max(0, Math.min(100, ((hit[0] - since) / span) * 100))}%` : '0'
  return (
    <div className="fb-hover-chart">
      <TimeChart points={points} label={label} since={since} until={until} format={format} height={height} />
      <div className="fb-hover-layer" style={{ height }} onMouseMove={move} onMouseLeave={() => setAt(null)}
        tabIndex={0} role="group" aria-label={label} onKeyDown={key} onBlur={() => setAt(null)}>
        {hit && (
          <>
            <span className="fb-hover-mark" style={{ left }} aria-hidden="true" />
            <span className={`fb-hover-note${(hit[0] - since) / span > 0.6 ? ' is-left' : ''}`} style={{ left }} role="status">
              {(span >= 86400 ? dateTime : clock)(hit[0])} · <b>{value(hit[1])}</b>
            </span>
          </>
        )}
      </div>
    </div>
  )
}
