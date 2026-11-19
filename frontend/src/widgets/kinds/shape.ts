import type { State, Tone, Widget } from '@/api/types'
import type { Kind, KindPick } from '../level'

/** What a widget's data can be drawn as. The first is its own kind. A stat counts anything; only
 *  time data draws as a graph; a gauge needs a scale and bars or a pie need numbers. */
export function kindsFor(w: Widget): Kind[] {
  switch (w.type) {
    case 'stat': return typeof w.value === 'number' && w.max != null ? ['stat', 'gauge'] : ['stat']
    case 'status': return ['status', 'stat', 'bar', 'pie', 'list', 'table']
    case 'list': return w.items.some((i) => i.number != null) ? ['list', 'bar', 'pie', 'stat', 'table'] : ['list', 'stat', 'table']
    case 'table': return ['table', 'stat', 'list']
    case 'sparkline': return w.max != null ? ['graph', 'stat', 'gauge'] : ['graph', 'stat']
    case 'series': return ['graph', 'stat']
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

export interface Part { label: string; value: number; max?: number; text: string; colour: string }

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
