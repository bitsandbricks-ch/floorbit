import type { State, Tone, Widget } from '@/api/types'
import type { Kind, KindPick } from '../level'

/** What each data shape (floorbit/plugins/widgets.py) can be drawn as. The first is its own kind.
 *  A stat counts anything; only time data draws as a graph. */
const KINDS: Record<Widget['type'], Kind[]> = {
  stat: ['stat'],
  status: ['status', 'stat', 'list', 'table'],
  list: ['list', 'stat', 'table'],
  table: ['table', 'stat', 'list'],
  sparkline: ['graph', 'stat'],
  series: ['graph', 'stat'],
}

export const kindsFor = (type: Widget['type']): Kind[] => KINDS[type] ?? ['stat']

/** The kind to draw: the pane's pick when the data allows it, else the data's own. */
export function resolveKind(w: Widget, pick: KindPick = 'auto'): Kind {
  const ok = kindsFor(w.type)
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
