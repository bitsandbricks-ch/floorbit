import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { clock, dayClock } from '@/lib/time'
import type { Level } from '../level'
import { type Threshold, useNumberStyle } from './display'
import { calc } from './combine'
import { type Axis, formatValue, type Line, lineColour, linesOf, type Look, stackLines, statOf, tipAt, trendOf } from './shape'

const LEGEND_H = 20
const AXIS_H = 18

/** Lines over time, drawn at the box's real size so text stays sharp: plain lines, areas, stacked
 *  or stacked to 100 %, with an optional dashed trend. Hover (or touch) shows the time and every
 *  line's value under the pointer. */
export function Graph({ widget, level, box, look = {} }: { widget: Widget; level: Level; box: { w: number; h: number }; look?: Look }) {
  const { t, i18n } = useTranslation()
  const style = useNumberStyle()
  const { lines: every, unit, timed } = linesOf(widget)
  // Comparison lines (yesterday) are drawn faint and dashed, over the time the real lines cover.
  const lines = every.filter((l) => !l.ghost)
  const [at, setAt] = useState<number | null>(null)
  const all = lines.flatMap((l) => l.points)
  const span = all.length ? [Math.min(...all.map((p) => p[0])), Math.max(...all.map((p) => p[0]))] : [0, 0]
  const ghosts = every.filter((l) => l.ghost).map((l) => ({ ...l, points: l.points.filter((p) => p[0] >= span[0] && p[0] <= span[1]) }))
    .filter((l) => l.points.length > 1)
  if (!all.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const stack = lines.length > 1 ? look.stack ?? 'none' : 'none'
  const area = look.style === 'area' || stack !== 'none'
  const trend = look.trend ?? 'none'
  const legend = look.legend?.length ? look.legend : null
  if (level === 's') {
    const s = statOf(widget, i18n.language, style)
    return (
      <div className="fb-w-graph-s">
        <div className="fb-w-stat-main"><span className="fb-w-stat-value">{s.value}</span>{s.unit && <span className="fb-w-stat-unit">{s.unit}</span>}</div>
        <Plot lines={lines} stack={stack} area={area} w={box.w} h={Math.max(16, box.h - 44)} />
      </div>
    )
  }
  const W = box.w
  const H = Math.max(40, box.h - LEGEND_H - (level === 'l' ? AXIS_H : 0))
  const t0 = Math.min(...all.map((p) => p[0]))
  const t1 = Math.max(...all.map((p) => p[0]))
  const stacked = stack !== 'none' ? stackLines(lines, stack) : null
  const axis = stack === 'percent' ? undefined : look.axis
  const top = stack === 'percent' ? 100 : axis?.max != null ? axis.max : Math.max(1, ...ghosts.flatMap((l) => l.points.map((p) => p[1])),
    ...(stacked ? stacked[stacked.length - 1].map((p) => p[2]) : all.map((p) => p[1])))
  const x = (ts: number) => ((ts - t0) / (t1 - t0 || 1)) * W
  const when = (ts: number) => (timed ? (t1 - t0 >= 86400 ? dayClock(ts) : clock(ts)) : '')
  const fmt = (v: number) => { const f = formatValue(v, unit, i18n.language, style); return `${f.value}${f.unit ? ` ${f.unit}` : ''}` }
  // The sample nearest the pointer, on the longest line: every line is read at that time.
  const base = lines.reduce((a, b) => (b.points.length > a.points.length ? b : a))
  const hover = at == null ? null : base.points.reduce((a, b) => (Math.abs(x(b[0]) - at) < Math.abs(x(a[0]) - at) ? b : a))
  const valueAt = (pts: [number, number][], ts: number) => pts.reduce((a, b) => (Math.abs(b[0] - ts) < Math.abs(a[0] - ts) ? b : a))[1]
  const sum = hover ? lines.reduce((a, l) => a + Math.max(0, valueAt(l.points, hover[0])), 0) : 0
  const trends = lines.map((l) => trendOf(l.points, trend))
  return (
    <div className="fb-w-graph">
      <div className="fb-w-legend">
        {lines.map((l, i) => {
          const last = l.points[l.points.length - 1]?.[1]
          return (
            <span key={i}>
              <i style={{ background: lineColour(l, i) }} />
              {l.label}
              {legend ? legend.map((c) => {
                const v = calc(l.points.map((p) => p[1]), c)
                return <em key={c} className="fb-w-calc">{t(`widgets.calc.${c}`)} <b>{v == null ? '–' : c === 'count' ? v : fmt(v)}</b></em>
              }) : last != null && <b>{fmt(last)}</b>}
              {!legend && level === 'l' && l.points.length > 1 && (
                <em>{t('widgets.kind.maxAvg', { max: fmt(Math.max(...l.points.map((p) => p[1]))),
                  avg: fmt(l.points.reduce((a, p) => a + p[1], 0) / l.points.length) })}</em>
              )}
            </span>
          )
        })}
        {ghosts.map((l, i) => <span key={`g${i}`} className="fb-w-ghost-key"><i />{l.label}</span>)}
      </div>
      <div className="fb-w-plot" onPointerMove={(e) => setAt(e.clientX - e.currentTarget.getBoundingClientRect().left)}
        onPointerLeave={() => setAt(null)}>
        <Plot lines={lines} stack={stack} area={area} trends={trends} steps={stack === 'percent' ? [] : look.thresholds} w={W} h={H} t0={t0} t1={t1} top={top} axis={axis} ghosts={stack === 'percent' ? [] : ghosts} cross={hover ? x(hover[0]) : null}
          label={t('widgets.kind.graphLabel', { name: widget.label || lines.map((l) => l.label).join(', ') })} />
        {hover && (
          <div className="fb-w-tip" role="tooltip" style={tipAt(x(hover[0]) - 10, x(hover[0]) + 10, W)}>
            {timed && <div className="fb-w-tip-when">{when(hover[0])}</div>}
            {lines.map((l, i) => {
              const v = valueAt(l.points, hover[0])
              return (
                <div key={i}>
                  <i style={{ background: lineColour(l, i) }} />{l.label}
                  <b>{fmt(v)}{stack === 'percent' && sum ? ` · ${Math.round((Math.max(0, v) / sum) * 100)} %` : ''}</b>
                </div>
              )
            })}
            {trend !== 'none' && trends.map((tr, i) => tr.length > 0 && (
              <div key={`t${i}`} className="fb-w-tip-trend">{t(`widgets.kind.trend.${trend}`)} · {lines[i].label}<b>{fmt(trendAt(tr, hover[0]))}</b></div>
            ))}
          </div>
        )}
      </div>
      {level === 'l' && (
        <div className="fb-w-axis"><span>{when(t0)}</span><span>{stack === 'percent' ? '100 %' : t('widgets.kind.top', { value: fmt(top) })}</span><span>{when(t1)}</span></div>
      )}
    </div>
  )
}

/** A trend's value at ``ts``: between its points on a straight line. */
function trendAt(tr: [number, number][], ts: number): number {
  if (tr.length === 1 || ts <= tr[0][0]) return tr[0][1]
  for (let i = 1; i < tr.length; i++) {
    if (ts <= tr[i][0]) {
      const [a, b] = [tr[i - 1], tr[i]]
      return a[1] + ((b[1] - a[1]) * (ts - a[0])) / (b[0] - a[0] || 1)
    }
  }
  return tr[tr.length - 1][1]
}

function Plot({ lines, stack, area, trends = [], steps = [], ghosts = [], w, h, t0, t1, top, axis, cross = null, label }: {
  lines: Line[]; stack: Look['stack']; area: boolean; trends?: [number, number][][]; steps?: Threshold[]; ghosts?: Line[]
  w: number; h: number; t0?: number; t1?: number; top?: number; axis?: Axis; cross?: number | null; label?: string
}) {
  const all = lines.flatMap((l) => l.points)
  const a = t0 ?? Math.min(...all.map((p) => p[0]))
  const b = t1 ?? Math.max(...all.map((p) => p[0]))
  const stacked = stack && stack !== 'none' ? stackLines(lines, stack) : null
  const hi = top ?? (stack === 'percent' ? 100 : stacked ? Math.max(1, ...stacked[stacked.length - 1].map((p) => p[2])) : Math.max(...all.map((p) => p[1]), 1))
  const x = (ts: number) => ((ts - a) / (b - a || 1)) * w
  // A log scale starts at the smallest value above 0 unless the axis sets its own; values outside
  // fixed ends sit on the edge instead of leaving the box.
  const lo = axis?.min ?? (axis?.log ? Math.min(hi, ...all.map((p) => p[1]).filter((v) => v > 0)) : 0)
  const sc = (v: number) => (axis?.log ? Math.log10(Math.max(v, lo)) : v)
  const y = (v: number) => h - 2 - Math.min(1, Math.max(0, (sc(v) - sc(lo)) / (sc(hi) - sc(lo) || 1))) * (h - 6)
  const xy = (ts: number, v: number) => `${x(ts).toFixed(1)},${y(v).toFixed(1)}`
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <line className="fb-w-base" x1={0} x2={w} y1={h - 1} y2={h - 1} />
      {lines.map((l, i) => {
        const colour = lineColour(l, i)
        if (stacked) {
          const band = stacked[i]
          const upper = band.map((p) => xy(p[0], p[2])).join(' ')
          const lower = [...band].reverse().map((p) => xy(p[0], p[1])).join(' ')
          return (
            <g key={i} style={{ color: colour }}>
              <polygon className="fb-w-fill stacked" points={`${upper} ${lower}`} />
              <polyline className="fb-w-line" points={upper} />
            </g>
          )
        }
        const pts = l.points.map((p) => xy(p[0], p[1])).join(' ')
        // Without a style, only the first line gets a soft fill, so overlapping lines stay readable.
        const fill = l.points.length > 1 && (area || i === 0)
        return (
          <g key={i} style={{ color: colour }}>
            {fill && <polygon className={`fb-w-fill${area ? ' area' : ''}`} points={`${x(l.points[0][0]).toFixed(1)},${h} ${pts} ${x(l.points[l.points.length - 1][0]).toFixed(1)},${h}`} />}
            <polyline className="fb-w-line" points={pts} />
          </g>
        )
      })}
      {trends.map((tr, i) => tr.length > 1 && (
        <polyline key={`t${i}`} className="fb-w-trend" style={{ color: lineColour(lines[i], i) }}
          points={tr.map((p) => xy(p[0], stack === 'percent' ? p[1] : p[1])).join(' ')} />
      ))}
      {steps.filter((st) => st.at > lo && st.at <= hi).map((st, i) => (
        <line key={`s${i}`} className={`fb-w-step fb-tone-${st.tone || 'none'}`} x1={0} x2={w} y1={y(st.at)} y2={y(st.at)} />
      ))}
      {ghosts.map((l, i) => <polyline key={`g${i}`} className="fb-w-ghost" points={l.points.map((p) => xy(p[0], p[1])).join(' ')} />)}
      {cross != null && <line className="fb-w-cross" x1={cross} x2={cross} y1={0} y2={h} />}
    </svg>
  )
}
