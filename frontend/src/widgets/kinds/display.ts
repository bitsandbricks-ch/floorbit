import { createContext, useContext } from 'react'
import type { Tone, Widget } from '@/api/types'
import { PALETTE, formatValue, numberColumns } from './shape'

/** How a pane shows its numbers (issue #960): colour steps, value mappings, unit and decimals,
 *  and which rows. Applied in the browser after the data is merged, grouped and calculated. */

/** From ``at`` up, a value takes this tone; ``percent`` compares the share of the max instead. */
export interface Threshold { at: number; tone: Tone }
/** A value from ``from`` to ``to`` (either open) shows as ``text``, in ``tone``. */
export interface Mapping { from?: number; to?: number; text: string; tone?: Tone }
export interface NumberStyle { decimals?: number; short?: boolean }
export type Sort = 'value-desc' | 'value-asc' | 'name-asc' | 'name-desc'
export const SORTS: Sort[] = ['value-desc', 'value-asc', 'name-asc', 'name-desc']

/** The colours a series or row can be given, named in the palette's order (floorbit/dashboards.py). */
export const SERIES_COLOURS = ['green', 'cyan', 'violet', 'pink', 'orange', 'blue', 'grey'] as const
export type SeriesColour = (typeof SERIES_COLOURS)[number]
export const seriesColour = (c: SeriesColour) => PALETTE[SERIES_COLOURS.indexOf(c)]
/** A series or row, found by its label: another name, a colour, or hidden. */
export interface Override { match: string; name?: string; colour?: SeriesColour; hide?: boolean }
export const MAX_OVERRIDES = 10

export interface Display extends NumberStyle {
  thresholds?: Threshold[]
  threshold_mode?: 'value' | 'percent'
  mappings?: Mapping[]
  unit?: string
  sort?: Sort
  limit?: number
  hide_zero?: boolean
  /** A graph's value axis: fixed ends, and a log scale (ends above 0). */
  y_min?: number
  y_max?: number
  y_log?: boolean
  overrides?: Override[]
}

export const NumberStyleContext = createContext<NumberStyle>({})
/** The pane's decimals and short numbers, for the kinds that format numbers. */
export const useNumberStyle = () => useContext(NumberStyleContext)

/** The tone for a value: the highest threshold it reaches. ``max`` turns it into a share. */
export function toneAt(v: number, d: Display, max?: number): Tone | null {
  if (!d.thresholds?.length) return null
  const x = d.threshold_mode === 'percent' ? (max ? (v / max) * 100 : null) : v
  if (x == null) return null
  let tone: Tone | null = null
  for (const t of [...d.thresholds].sort((a, b) => a.at - b.at)) if (x >= t.at) tone = t.tone
  return tone
}

export function mappingFor(v: number, d: Display): Mapping | null {
  return d.mappings?.find((m) => (m.from == null || v >= m.from) && (m.to == null || v <= m.to)) ?? null
}

const text = (v: number, unit: string, d: Display, lang?: string) => {
  const f = formatValue(v, unit, lang, d)
  return `${f.value}${f.unit ? ` ${f.unit}` : ''}`
}

/** The widget as the pane shows it: unit, mappings, tones from thresholds, then sort and top N. */
export function applyDisplay(w: Widget, d: Display, lang?: string): Widget {
  switch (w.type) {
    case 'stat': {
      const unit = d.unit ?? w.unit
      if (typeof w.value !== 'number') return { ...w, unit }
      const m = mappingFor(w.value, d)
      const tone = m?.tone ?? toneAt(w.value, d, w.max) ?? w.tone
      return { ...w, unit: m ? '' : unit, tone, text: m?.text }
    }
    case 'sparkline':
      return d.unit != null ? { ...w, unit: d.unit } : w
    case 'series': {
      const series = overridden(w.series, d.overrides, (s, o) => ({ ...s, label: o.name || s.label, ...(o.colour ? { colour: seriesColour(o.colour) } : {}) }))
      return { ...w, series, unit: d.unit ?? w.unit }
    }
    case 'list': {
      let items = overridden(w.items, d.overrides, (i, o) => ({ ...i, label: o.name || i.label, ...(o.colour ? { colour: seriesColour(o.colour) } : {}) })).map((i) => {
        if (i.number == null) return i
        const m = mappingFor(i.number, d)
        const tone = m?.tone ?? toneAt(i.number, d, i.max) ?? i.tone
        const changed = m || d.unit != null || d.decimals != null || d.short
        // A value with its own max reads "21 / 24": keep that, only re-tone it.
        const value = m ? m.text : changed && i.max == null ? text(i.number, d.unit ?? '', d, lang) : i.value
        return { ...i, tone, value }
      })
      if (d.hide_zero) items = items.filter((i) => i.number == null || i.number !== 0)
      items = sortRows(items, d.sort, (i) => i.number ?? null, (i) => i.label)
      return { ...w, items: d.limit ? items.slice(0, d.limit) : items }
    }
    case 'status': {
      const items = sortRows(w.items, d.sort?.startsWith('name') ? d.sort : undefined, () => null, (i) => i.label)
      return { ...w, items: d.limit ? items.slice(0, d.limit) : items }
    }
    case 'table': {
      // The value of a row is its last number column: labels come first.
      const num = numberColumns(w).pop()
      let rows = d.hide_zero && num ? w.rows.filter((r) => Number(r[num]) !== 0) : w.rows
      rows = sortRows(rows, d.sort, (r) => (num ? Number(r[num]) : null), (r) => r[w.columns[0]?.key] ?? '')
      if (num && d.mappings?.length) rows = rows.map((r) => { const m = mappingFor(Number(r[num]), d); return m ? { ...r, [num]: m.text } : r })
      return { ...w, rows: d.limit ? rows.slice(0, d.limit) : rows }
    }
  }
}

/** Applies the per-series settings: hidden ones go, the rest are renamed or recoloured. */
function overridden<T extends { label: string }>(rows: T[], overrides: Override[] | undefined, apply: (r: T, o: Override) => T): T[] {
  if (!overrides?.length) return rows
  return rows.flatMap((r) => {
    const o = overrides.find((x) => x.match === r.label)
    return !o ? [r] : o.hide ? [] : [apply(r, o)]
  })
}

function sortRows<T>(rows: T[], sort: Sort | undefined, value: (r: T) => number | null, name: (r: T) => string): T[] {
  if (!sort) return rows
  const dir = sort.endsWith('asc') ? 1 : -1
  const out = [...rows]
  if (sort.startsWith('name')) out.sort((a, b) => dir * name(a).localeCompare(name(b), undefined, { numeric: true }))
  else out.sort((a, b) => dir * ((value(a) ?? -Infinity) - (value(b) ?? -Infinity)))
  return out
}

/** The labels a pane can set a name, colour or hide for: a graph's series, or a list's rows. */
export function seriesLabels(w: Widget): string[] {
  if (w.type === 'series') return w.series.map((s) => s.label)
  if (w.type === 'list') return [...new Set(w.items.map((i) => i.label))].slice(0, 100)
  return []
}

/** Which display settings mean something for this data: numbers to format and colour, rows to
 *  sort and cut. */
export function displaysFor(w: Widget): { numbers: boolean; colours: boolean; rows: boolean } {
  const numbers = (w.type === 'stat' && typeof w.value === 'number') || w.type === 'sparkline' || w.type === 'series'
    || (w.type === 'list' && w.items.some((i) => i.number != null)) || numberColumns(w).length > 0
  return { numbers, colours: numbers, rows: w.type === 'list' || w.type === 'status' || w.type === 'table' }
}
