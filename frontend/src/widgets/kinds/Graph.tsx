import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { clock, dayClock } from '@/lib/time'
import type { Level } from '../level'
import { formatValue, linesOf, statOf } from './shape'

/** Line colours in order: accent, trace, then two that never read as up or down. */
const COLOURS = ['var(--color-bit)', 'var(--color-trace)', '#a78bfa', '#f472b6']
const LEGEND_H = 20
const AXIS_H = 18

/** Lines over time, drawn at the box's real size so text stays sharp. Hover (or touch) shows the
 *  time and every line's value under the pointer. */
export function Graph({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const { lines, unit, timed } = linesOf(widget)
  const [at, setAt] = useState<number | null>(null)
  const all = lines.flatMap((l) => l.points)
  if (!all.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  if (level === 's') {
    const s = statOf(widget, i18n.language)
    return (
      <div className="fb-w-graph-s">
        <div className="fb-w-stat-main"><span className="fb-w-stat-value">{s.value}</span>{s.unit && <span className="fb-w-stat-unit">{s.unit}</span>}</div>
        <Plot lines={lines} w={box.w} h={Math.max(16, box.h - 44)} />
      </div>
    )
  }
  const W = box.w
  const H = Math.max(40, box.h - LEGEND_H - (level === 'l' ? AXIS_H : 0))
  const t0 = Math.min(...all.map((p) => p[0]))
  const t1 = Math.max(...all.map((p) => p[0]))
  const top = Math.max(...all.map((p) => p[1]), 1)
  const x = (ts: number) => ((ts - t0) / (t1 - t0 || 1)) * W
  const when = (ts: number) => (timed ? (t1 - t0 >= 86400 ? dayClock(ts * 1000) : clock(ts * 1000)) : '')
  const fmt = (v: number) => { const f = formatValue(v, unit, i18n.language); return `${f.value}${f.unit ? ` ${f.unit}` : ''}` }
  // The sample nearest the pointer, on the longest line: every line is read at that time.
  const base = lines.reduce((a, b) => (b.points.length > a.points.length ? b : a))
  const hover = at == null ? null : base.points.reduce((a, b) => (Math.abs(x(b[0]) - at) < Math.abs(x(a[0]) - at) ? b : a))
  const valueAt = (pts: [number, number][], ts: number) => pts.reduce((a, b) => (Math.abs(b[0] - ts) < Math.abs(a[0] - ts) ? b : a))[1]
  return (
    <div className="fb-w-graph">
      <div className="fb-w-legend">
        {lines.map((l, i) => {
          const last = l.points[l.points.length - 1]?.[1]
          return (
            <span key={i}>
              <i style={{ background: COLOURS[i % COLOURS.length] }} />
              {l.label}
              {last != null && <b>{fmt(last)}</b>}
              {level === 'l' && l.points.length > 1 && (
                <em>{t('widgets.kind.maxAvg', { max: fmt(Math.max(...l.points.map((p) => p[1]))),
                  avg: fmt(l.points.reduce((a, p) => a + p[1], 0) / l.points.length) })}</em>
              )}
            </span>
          )
        })}
      </div>
      <div className="fb-w-plot" onPointerMove={(e) => setAt(e.clientX - e.currentTarget.getBoundingClientRect().left)}
        onPointerLeave={() => setAt(null)}>
        <Plot lines={lines} w={W} h={H} t0={t0} t1={t1} top={top} cross={hover ? x(hover[0]) : null}
          label={t('widgets.kind.graphLabel', { name: widget.label || lines.map((l) => l.label).join(', ') })} />
        {hover && (
          <div className="fb-w-tip" role="tooltip" style={{ left: Math.min(Math.max(x(hover[0]) + 10, 0), Math.max(0, W - 170)) }}>
            {timed && <div className="fb-w-tip-when">{when(hover[0])}</div>}
            {lines.map((l, i) => (
              <div key={i}><i style={{ background: COLOURS[i % COLOURS.length] }} />{l.label}<b>{fmt(valueAt(l.points, hover[0]))}</b></div>
            ))}
          </div>
        )}
      </div>
      {level === 'l' && (
        <div className="fb-w-axis"><span>{when(t0)}</span><span>{t('widgets.kind.top', { value: fmt(top) })}</span><span>{when(t1)}</span></div>
      )}
    </div>
  )
}

function Plot({ lines, w, h, t0, t1, top, cross = null, label }: {
  lines: { points: [number, number][] }[]; w: number; h: number; t0?: number; t1?: number; top?: number; cross?: number | null; label?: string
}) {
  const all = lines.flatMap((l) => l.points)
  const a = t0 ?? Math.min(...all.map((p) => p[0]))
  const b = t1 ?? Math.max(...all.map((p) => p[0]))
  const hi = top ?? Math.max(...all.map((p) => p[1]), 1)
  const x = (ts: number) => ((ts - a) / (b - a || 1)) * w
  const y = (v: number) => h - 2 - (v / hi) * (h - 6)
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <line className="fb-w-base" x1={0} x2={w} y1={h - 1} y2={h - 1} />
      {lines.map((l, i) => {
        const pts = l.points.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ')
        return (
          <g key={i} style={{ color: COLOURS[i % COLOURS.length] }}>
            {i === 0 && l.points.length > 1 && <polygon className="fb-w-fill" points={`${x(l.points[0][0]).toFixed(1)},${h} ${pts} ${x(l.points[l.points.length - 1][0]).toFixed(1)},${h}`} />}
            <polyline className="fb-w-line" points={pts} />
          </g>
        )
      })}
      {cross != null && <line className="fb-w-cross" x1={cross} x2={cross} y1={0} y2={h} />}
    </svg>
  )
}
