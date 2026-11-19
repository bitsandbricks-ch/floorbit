import type { State, Tone, Widget } from '@/api/types'
import type { Kind, KindPick } from '../level'

/** What a widget's data can be drawn as. The first is its own kind. A stat counts anything; only
 *  time data draws as a graph; a gauge needs a scale and bars or a pie need numbers. */
export function kindsFor(w: Widget): Kind[] {
  switch (w.type) {
    case 'stat': return typeof w.value === 'number' && w.max != null ? ['stat', 'gauge'] : ['stat']
    case 'status': return ['status', 'stat', 'bar', 'column', 'pie', 'list', 'table']
    case 'list': return w.items.some((i) => i.number != null) ? ['list', 'bar', 'column', 'pie', 'histogram', 'stat', 'table'] : ['list', 'stat', 'table']
    case 'table': return numberColumns(w).length ? ['table', 'bar', 'column', 'histogram', 'stat', 'list'] : ['table', 'stat', 'list']
    case 'sparkline': return w.max != null ? ['graph', 'column', 'histogram', 'stat', 'gauge'] : ['graph', 'column', 'histogram', 'stat']
    case 'series': return ['graph', 'column', 'histogram', 'stat']
    default: return ['stat']
  }
}

/** The kind to draw: the pane's pick when the data allows it, else the data's own. */
export function resolveKind(w: Widget, pick: KindPick = 'auto'): Kind {
  const ok = kindsFor(w)
  return pick !== 'auto' && ok.includes(pick) ? pick : ok[0]
}

const SI = ['', 'k', 'M', 'G', 'T']

/** A number for a tile: bits and bytes scale (5.2 Gbit/s), counts get thousands separators. */
export function formatValue(v: number, unit = '', lang?: string): { value: string; unit: string } {
  if (/^(bit|B)(\/s)?$/.test(unit) && Math.abs(v) >= 1000) {
    let i = 0
    while (Math.abs(v) >= 1000 && i < SI.length - 1) { v /= 1000; i++ }
    return { value: v.toLocaleString(lang, { maximumFractionDigits: v < 10 ? 1 : 0 }), unit: `${SI[i]}${unit}` }
  }
  return { value: v.toLocaleString(lang, { maximumFractionDigits: Math.abs(v) < 10 ? 2 : 1 }), unit }
}

const BAD: Record<State, number> = { down: 0, warn: 1, unknown: 2, up: 3 }

export interface StatData { value: string; unit: string; tone: Tone; of?: number }

/** One number for any shape: a stat as is, how many are up, how many rows, the latest reading. */
export function statOf(w: Widget, lang?: string): StatData {
  switch (w.type) {
    case 'stat':
      return typeof w.value === 'number' ? { ...formatValue(w.value, w.unit, lang), tone: w.tone } : { value: w.value, unit: w.unit, tone: w.tone }
    case 'status': {
      const up = w.items.filter((i) => i.state === 'up').length
      const tone: Tone = w.items.some((i) => i.state === 'down') ? 'err' : w.items.some((i) => i.state === 'warn') ? 'warn' : w.items.length ? 'ok' : ''
      return { value: up.toLocaleString(lang), unit: '', tone, of: w.items.length }
    }
    case 'list': return { value: w.items.length.toLocaleString(lang), unit: '', tone: '' }
    case 'table': return { value: w.rows.length.toLocaleString(lang), unit: '', tone: '' }
    case 'sparkline': {
      const v = w.value ?? w.points[w.points.length - 1]
      return v == null ? { value: '–', unit: w.unit, tone: '' } : { ...formatValue(v, w.unit, lang), tone: '' }
    }
    case 'series': {
      const pts = w.series[0]?.points ?? []
      const v = pts[pts.length - 1]?.[1]
      return v == null ? { value: '–', unit: w.unit, tone: '' } : { ...formatValue(v, w.unit, lang), tone: '' }
    }
  }
}

export interface Column { key: string; label: string }
export interface Row { cells: Record<string, string>; state?: State; tone?: Tone }

/** Rows for a list or table: status items worst first, so the problem is what fits. */
export function rowsOf(w: Widget, labels: { name: string; value: string; state: string }): { columns: Column[]; rows: Row[] } {
  switch (w.type) {
    case 'status':
      return {
        columns: [{ key: 'label', label: labels.name }, { key: 'detail', label: labels.state }],
        rows: [...w.items].sort((a, b) => BAD[a.state] - BAD[b.state])
          .map((i) => ({ cells: { label: i.label, detail: i.detail }, state: i.state })),
      }
    case 'list':
      return {
        columns: [{ key: 'label', label: labels.name }, { key: 'value', label: labels.value }],
        rows: w.items.map((i) => ({ cells: { label: i.label, value: i.value }, tone: i.tone })),
      }
    case 'table':
      return { columns: w.columns, rows: w.rows.map((r) => ({ cells: r })) }
    default:
      return { columns: [], rows: [] }
  }
}

export interface Line { label: string; points: [number, number][] }

/** Lines over time. A sparkline has no times: its points are evenly spaced. */
export function linesOf(w: Widget): { lines: Line[]; unit: string; timed: boolean } {
  if (w.type === 'series') return { lines: w.series, unit: w.unit, timed: true }
  if (w.type === 'sparkline') return { lines: [{ label: w.label, points: w.points.map((v, i) => [i, v]) }], unit: w.unit, timed: false }
  return { lines: [], unit: '', timed: false }
}

/** How many of each state, worst first, for a status at its small level. */
export function stateCounts(w: Widget): [State, number][] {
  if (w.type !== 'status') return []
  const n: Partial<Record<State, number>> = {}
  for (const i of w.items) n[i.state] = (n[i.state] ?? 0) + 1
  return (Object.keys(BAD) as State[]).filter((s) => n[s]).map((s) => [s, n[s]!])
}

export interface Segment { label: string; value: number; colour: string }
/** One bar: its value, or (a table row) the sum of its segments, one per number column. */
export interface Part { label: string; value: number; max?: number; text: string; colour: string; segments?: Segment[] }

/** How bars and lines with more than one series sit: next to each other (or over each other, for
 *  lines), stacked, or stacked to 100 %. */
export type Stack = 'none' | 'stacked' | 'percent'
export const STACKS: Stack[] = ['none', 'stacked', 'percent']
export type LineStyle = 'line' | 'area'
export const LINE_STYLES: LineStyle[] = ['line', 'area']
/** A dashed line over each series: a straight fit over the time shown, or a rolling average. */
export type Trend = 'none' | 'linear' | 'average'
export const TRENDS: Trend[] = ['none', 'linear', 'average']
export interface Look { stack?: Stack; style?: LineStyle; trend?: Trend }

/** Which look options mean something for this data drawn as this kind: stacking needs two or
 *  more series (or number columns), the line style needs a graph, a trend needs time. */
export function looksFor(w: Widget, kind: Kind): (keyof Look)[] {
  const timed = w.type === 'series' || w.type === 'sparkline'
  const many = w.type === 'series' ? w.series.length > 1 : numberColumns(w).length > 1
  const out: (keyof Look)[] = []
  if (many && ['graph', 'column', 'bar'].includes(kind)) out.push('stack')
  if (kind === 'graph') out.push('style')
  if (timed && (kind === 'graph' || kind === 'column')) out.push('trend')
  return out
}

/** Columns of a table where every row holds a plain number. */
export function numberColumns(w: Widget): string[] {
  if (w.type !== 'table' || !w.rows.length) return []
  return w.columns.map((c) => c.key).filter((k) => w.rows.every((r) => isNumber(r[k])))
}
const isNumber = (v: string | undefined) => v != null && v.trim() !== '' && Number.isFinite(Number(v))

/** State colours, fixed like the dots: a theme never changes what "down" looks like. */
export const STATE_COLOUR: Record<State, string> = {
  down: 'var(--color-down)', warn: 'var(--color-warn)', unknown: 'var(--color-unknown)', up: 'var(--color-up)',
}
const TONE_COLOUR: Record<string, string> = { err: 'var(--color-down)', warn: 'var(--color-warn)', ok: 'var(--color-up)' }
/** Categories that are not states: accent, trace, then colours that never read as up or down. */
export const PALETTE = ['var(--color-bit)', 'var(--color-trace)', '#a78bfa', '#f472b6', '#fb923c', '#60a5fa', '#94a3b8']

/** Numbered parts for bars and a pie: how many in each state, or a list's numbers. */
export function partsOf(w: Widget, stateLabel: (s: State) => string, lang?: string): Part[] {
  if (w.type === 'status') {
    return stateCounts(w).map(([s, n]) => ({ label: stateLabel(s), value: n, text: n.toLocaleString(lang), colour: STATE_COLOUR[s] }))
  }
  if (w.type === 'list') {
    return w.items.filter((i) => i.number != null).map((i, k) => ({
      label: i.label, value: i.number!, max: i.max, text: i.value || i.number!.toLocaleString(lang),
      colour: (i.tone && TONE_COLOUR[i.tone]) || PALETTE[i.max != null ? 0 : k % PALETTE.length],
    }))
  }
  if (w.type === 'table') {
    const nums = numberColumns(w)
    if (!nums.length) return []
    const name = w.columns.find((c) => !nums.includes(c.key))?.key
    return w.rows.map((r, k) => {
      const segments = nums.map((key, i) => ({ label: w.columns.find((c) => c.key === key)!.label, value: Number(r[key]), colour: PALETTE[i % PALETTE.length] }))
      const value = segments.reduce((a, g) => a + g.value, 0)
      return { label: name ? r[name] ?? '' : String(k + 1), value, text: value.toLocaleString(lang), colour: PALETTE[0],
        ...(segments.length > 1 ? { segments } : {}) }
    })
  }
  return []
}

/** A pie reads up to seven slices; the smallest rest become one "other" slice. */
export function slices(parts: Part[], other: string, lang?: string): Part[] {
  const sorted = [...parts].filter((p) => p.value > 0).sort((a, b) => b.value - a.value)
  if (sorted.length <= 7) return sorted
  const rest = sorted.slice(6).reduce((a, p) => a + p.value, 0)
  return [...sorted.slice(0, 6), { label: other, value: rest, text: rest.toLocaleString(lang), colour: 'var(--color-faint)' }]
}

/** A stat or sparkline on its scale, for a gauge. */
export function scaleOf(w: Widget): { value: number; min: number; max: number } | null {
  if (w.type === 'stat' && typeof w.value === 'number' && w.max != null) return { value: w.value, min: w.min ?? 0, max: w.max }
  if (w.type === 'sparkline' && w.max != null) {
    const v = w.value ?? w.points[w.points.length - 1]
    return v == null ? null : { value: v, min: w.min ?? 0, max: w.max }
  }
  return null
}

export interface Bucket { from: number; to: number; values: (number | null)[] }

/** Time data in at most ``n`` columns: each the average of the samples in its slice of time, one
 *  value per line (null where a line has no sample in it). */
export function bucketsOf(lines: Line[], n: number): Bucket[] {
  const all = lines.flatMap((l) => l.points)
  if (!all.length || n < 1) return []
  const t0 = Math.min(...all.map((p) => p[0]))
  const t1 = Math.max(...all.map((p) => p[0]))
  const count = Math.max(1, Math.min(n, Math.max(...lines.map((l) => l.points.length))))
  const step = (t1 - t0) / count || 1
  const out: Bucket[] = Array.from({ length: count }, (_, i) => ({ from: t0 + i * step, to: t0 + (i + 1) * step, values: [] }))
  lines.forEach((l, li) => {
    const sums = new Array(count).fill(0), ns = new Array(count).fill(0)
    for (const [t, v] of l.points) {
      const i = Math.min(count - 1, Math.floor((t - t0) / step))
      sums[i] += v
      ns[i] += 1
    }
    out.forEach((b, i) => { b.values[li] = ns[i] ? sums[i] / ns[i] : null })
  })
  return out
}

/** Stacked lines: per sample of the longest line, each line's [time, bottom, top]. Lines are read
 *  at the nearest sample, so lines sampled at slightly different times still stack. */
export function stackLines(lines: Line[], mode: Stack): [number, number, number][][] {
  if (!lines.length) return []
  const base = lines.reduce((a, b) => (b.points.length > a.points.length ? b : a))
  const at = (pts: [number, number][], t: number) =>
    pts.length ? pts.reduce((a, b) => (Math.abs(b[0] - t) < Math.abs(a[0] - t) ? b : a))[1] : 0
  const values = base.points.map(([t]) => lines.map((l) => Math.max(0, at(l.points, t))))
  return lines.map((_, li) => base.points.map(([t], k) => {
    const row = values[k]
    const sum = row.reduce((a, v) => a + v, 0) || 1
    const scale = mode === 'percent' ? 100 / sum : 1
    const lo = row.slice(0, li).reduce((a, v) => a + v, 0) * scale
    return [t, lo, lo + row[li] * scale] as [number, number, number]
  }))
}

/** All the numbers a widget holds, for a histogram: a list's or table's numbers, or every sample. */
export function valuesOf(w: Widget): number[] {
  switch (w.type) {
    case 'list': return w.items.filter((i) => i.number != null).map((i) => i.number!)
    case 'table': { const k = numberColumns(w)[0]; return k ? w.rows.map((r) => Number(r[k])) : [] }
    case 'sparkline': return w.points
    case 'series': return w.series.flatMap((l) => l.points.map((p) => p[1]))
    default: return []
  }
}

export interface Bin { from: number; to: number; count: number }

/** Values counted in ranges of a round width (1, 2 or 5 times a power of ten), about the square
 *  root of the count of ranges and at most ``most``. */
export function binsOf(values: number[], most = 20): Bin[] {
  if (!values.length) return []
  const lo = Math.min(...values), hi = Math.max(...values)
  if (lo === hi) return [{ from: lo, to: hi, count: values.length }]
  const want = Math.max(2, Math.min(most, Math.ceil(Math.sqrt(values.length))))
  const raw = (hi - lo) / want
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((f) => f * mag).find((x) => x >= raw)!
  const start = Math.floor(lo / step) * step
  const n = Math.max(1, Math.ceil((hi - start) / step + 1e-9))
  const bins: Bin[] = Array.from({ length: n }, (_, i) => ({ from: start + i * step, to: start + (i + 1) * step, count: 0 }))
  for (const v of values) bins[Math.min(n - 1, Math.floor((v - start) / step))].count++
  return bins
}

/** The trend of one line, at its own sample times. A rolling average spans about a twelfth of the
 *  samples (at least three); a linear fit is the least-squares line. */
export function trendOf(points: [number, number][], mode: Trend): [number, number][] {
  if (mode === 'none' || points.length < 2) return []
  if (mode === 'average') {
    const half = Math.max(1, Math.round(points.length / 24))
    return points.map(([t], i) => {
      const win = points.slice(Math.max(0, i - half), i + half + 1)
      return [t, win.reduce((a, p) => a + p[1], 0) / win.length]
    })
  }
  const n = points.length
  const mx = points.reduce((a, p) => a + p[0], 0) / n
  const my = points.reduce((a, p) => a + p[1], 0) / n
  const sxx = points.reduce((a, p) => a + (p[0] - mx) ** 2, 0)
  const slope = sxx ? points.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0) / sxx : 0
  return [points[0], points[n - 1]].map(([t]) => [t, my + slope * (t - mx)] as [number, number])
}

/** A part's tooltip: its value, its share of its own max, and each segment. */
export function partTip(part: Part, pct: number): string {
  const head = part.max != null ? `${part.label}: ${part.text} (${Math.round(pct)} %)` : `${part.label}: ${part.text}`
  return part.segments ? `${head}\n${part.segments.map((g) => `${g.label}: ${g.value}`).join('\n')}` : head
}


/** Where a tooltip sits: right of what it describes in the left half, left of it in the right
 *  half, so a wide tooltip never runs out of the box. */
export function tipAt(from: number, to: number, width: number): { left?: number; right?: number } {
  return to <= width / 2 ? { left: Math.max(0, to) } : { right: Math.max(0, width - from) }
}
