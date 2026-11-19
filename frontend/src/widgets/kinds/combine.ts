import type { Widget } from '@/api/types'
import { formatValue, linesOf, numberColumns, valuesOf } from './shape'

/** What a pane does to its data before drawing it (issue #959): more sources merged in, rows
 *  grouped by a key, and calculations. All of it runs here, on the shapes the widgets already
 *  return, so plugins need nothing new. */

export type Calc = 'count' | 'sum' | 'avg' | 'min' | 'max' | 'first' | 'last'
export const CALCS: Calc[] = ['count', 'sum', 'avg', 'min', 'max', 'first', 'last']
export const MAX_SOURCES = 4

export function calc(values: number[], c: Calc): number | null {
  if (c === 'count') return values.length
  if (!values.length) return null
  switch (c) {
    case 'sum': return values.reduce((a, v) => a + v, 0)
    case 'avg': return values.reduce((a, v) => a + v, 0) / values.length
    case 'min': return Math.min(...values)
    case 'max': return Math.max(...values)
    case 'first': return values[0]
    case 'last': return values[values.length - 1]
  }
}

type Family = 'time' | 'steps' | 'number' | 'rows'
function family(w: Widget): Family {
  if (w.type === 'series') return 'time'
  if (w.type === 'sparkline') return 'steps'
  if (w.type === 'stat') return 'number'
  return 'rows'
}

interface Table { columns: { key: string; label: string }[]; rows: Record<string, string>[] }

/** Any row shape as a table whose first column is the label to join on. */
function tableOf(w: Widget, names: { name: string; value: string; state: string; detail: string }): Table {
  switch (w.type) {
    case 'status':
      return { columns: [{ key: 'label', label: names.name }, { key: 'state', label: names.state }, { key: 'detail', label: names.detail }],
        rows: w.items.map((i) => ({ label: i.label, state: i.state, detail: i.detail })) }
    case 'list':
      return { columns: [{ key: 'label', label: names.name }, { key: 'value', label: w.label }],
        rows: w.items.map((i) => ({ label: i.label, value: i.number != null ? String(i.number) : i.value })) }
    case 'table': return { columns: w.columns, rows: w.rows }
    default: return { columns: [], rows: [] }
  }
}

export interface Merged { widget: Widget; dropped: string[] }

/** Several widgets as one. The first decides the shape: lines over time gain the others' lines
 *  (same unit only), numbers become a list with one item per source, lists and tables join on
 *  their first column and status lists add up. A source that can't join is left out and named. */
export function merge(ws: Widget[], names = { name: 'Name', value: 'Value', state: 'State', detail: 'Detail' }): Merged {
  const [first, ...rest] = ws
  if (!rest.length) return { widget: first, dropped: [] }
  const fam = family(first)
  const fits = rest.filter((w) => family(w) === fam
    && (fam !== 'time' && fam !== 'steps' || linesOf(w).unit === linesOf(first).unit)
    && (fam !== 'number' || typeof (w as { value?: unknown }).value === 'number'))
  const dropped = rest.filter((w) => !fits.includes(w)).map((w) => w.label)
  const all = [first, ...fits]
  if (all.length === 1) return { widget: first, dropped }
  if (fam === 'time' || fam === 'steps') {
    const series = all.flatMap((w) => {
      const { lines } = linesOf(w)
      return lines.map((l) => ({ label: lines.length === 1 ? w.label : `${w.label} · ${l.label}`, points: l.points }))
    }).slice(0, 8)
    return { widget: { ...first, type: 'series', unit: linesOf(first).unit, series }, dropped }
  }
  if (fam === 'number') {
    const items = all.map((w) => {
      const s = w as Extract<Widget, { type: 'stat' }>
      const f = formatValue(s.value as number, s.unit)
      return { label: w.label, value: `${f.value}${f.unit ? ` ${f.unit}` : ''}`, tone: s.tone, number: s.value as number, max: s.max }
    })
    return { widget: { ...first, type: 'list', items }, dropped }
  }
  if (all.every((w) => w.type === 'status')) {
    return { widget: { ...first, type: 'status', items: all.flatMap((w) => (w as Extract<Widget, { type: 'status' }>).items) }, dropped }
  }
  // Join on the first column: one row per label, each source's other columns side by side.
  const tables = all.map((w) => tableOf(w, names))
  const columns = [{ key: 'label', label: tables[0].columns[0]?.label ?? names.name }]
  tables.forEach((tb, i) => tb.columns.slice(1).forEach((c) => {
    columns.push({ key: `${i}.${c.key}`, label: tables.length > 1 && tb.columns.length > 2 ? `${all[i].label} · ${c.label}` : c.label })
  }))
  const byLabel = new Map<string, Record<string, string>>()
  tables.forEach((tb, i) => {
    const head = tb.columns[0]?.key
    if (!head) return
    for (const r of tb.rows) {
      const label = r[head] ?? ''
      const row = byLabel.get(label) ?? { label }
      tb.columns.slice(1).forEach((c) => { row[`${i}.${c.key}`] = r[c.key] ?? '' })
      byLabel.set(label, row)
    }
  })
  // A row one source lacks gets empty cells, so it reads as missing rather than as zero.
  const rows = [...byLabel.values()].map((r) => Object.fromEntries(columns.map((c) => [c.key, r[c.key] ?? ''])))
  return { widget: { ...first, type: 'table', columns, rows }, dropped }
}

/** Keys the rows can be grouped by. Any table column may be one: a hall or block number is a
 *  number column too. */
export function groupKeys(w: Widget): { key: string; label: string }[] {
  switch (w.type) {
    case 'status': return [{ key: 'state', label: 'state' }, { key: 'detail', label: 'detail' }]
    case 'list': return [{ key: 'value', label: 'value' }]
    case 'table': return w.columns
    default: return []
  }
}

/** Rows grouped by ``key``: one item per group, its number the calculation over the last number
 *  column other than the key (values come after labels), or how many rows for a count or when
 *  there are no numbers. Biggest first. */
export function groupBy(w: Widget, key: string, c: Calc = 'count', lang?: string, stateName: (s: string) => string = (s) => s): Widget {
  const rows: { group: string; number?: number }[] = []
  if (w.type === 'status') w.items.forEach((i) => rows.push({ group: key === 'state' ? stateName(i.state) : i.detail }))
  else if (w.type === 'list') w.items.forEach((i) => rows.push({ group: i.value, number: i.number }))
  else if (w.type === 'table') {
    const num = numberColumns(w).filter((k) => k !== key).pop()
    w.rows.forEach((r) => rows.push({ group: r[key] ?? '', number: num ? Number(r[num]) : undefined }))
  } else return w
  const groups = new Map<string, number[]>()
  for (const r of rows) {
    const g = groups.get(r.group) ?? []
    if (r.number != null) g.push(r.number)
    else g.push(NaN)
    groups.set(r.group, g)
  }
  const items = [...groups.entries()].map(([group, vs]) => {
    const nums = vs.filter((v) => !Number.isNaN(v))
    const n = c === 'count' || !nums.length ? vs.length : calc(nums, c) ?? 0
    return { label: group || '–', value: formatValue(n, '', lang).value, tone: '' as const, number: n }
  }).sort((a, b) => b.number - a.number)
  return { ...w, type: 'list', items }
}

/** The data as one number (a stat), or one per line when there are several lines. */
export function reduce(w: Widget, c: Calc, lang?: string): Widget {
  const { lines, unit } = linesOf(w)
  if (lines.length > 1) {
    const items = lines.map((l) => {
      const n = calc(l.points.map((p) => p[1]), c) ?? 0
      const f = formatValue(n, c === 'count' ? '' : unit, lang)
      return { label: l.label, value: `${f.value}${f.unit ? ` ${f.unit}` : ''}`, tone: '' as const, number: n }
    })
    return { ...w, type: 'list', items }
  }
  const count = w.type === 'status' ? w.items.length : w.type === 'list' ? w.items.length : w.type === 'table' ? w.rows.length : undefined
  const values = valuesOf(w)
  const n = c === 'count' && count != null ? count : calc(values, c)
  return { ...w, type: 'stat', value: n ?? '–', unit: c === 'count' ? '' : unit, tone: '' }
}

export interface Shaping { group_by?: string; reduce?: Calc }

/** The whole pipeline: merge the sources, then group or reduce. */
export function shapeData(ws: Widget[], how: Shaping, lang?: string, names?: Parameters<typeof merge>[1],
  stateName?: (s: string) => string): Merged {
  const merged = merge(ws, names)
  let w = merged.widget
  if (how.group_by && groupKeys(w).some((k) => k.key === how.group_by)) w = groupBy(w, how.group_by, how.reduce ?? 'count', lang, stateName)
  else if (how.reduce) w = reduce(w, how.reduce, lang)
  return { widget: w, dropped: merged.dropped }
}
