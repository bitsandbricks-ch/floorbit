import { createContext, useContext } from 'react'
import type { Tone, Widget } from '@/api/types'
import { formatValue, numberColumns } from './shape'

/** How a pane shows its numbers (issue #960): colour steps, value mappings, unit and decimals,
 *  and which rows. Applied in the browser after the data is merged, grouped and calculated. */

/** From ``at`` up, a value takes this tone; ``percent`` compares the share of the max instead. */
export interface Threshold { at: number; tone: Tone }
/** A value from ``from`` to ``to`` (either open) shows as ``text``, in ``tone``. */
export interface Mapping { from?: number; to?: number; text: string; tone?: Tone }
export interface NumberStyle { decimals?: number; short?: boolean }
export type Sort = 'value-desc' | 'value-asc' | 'name-asc' | 'name-desc'
export const SORTS: Sort[] = ['value-desc', 'value-asc', 'name-asc', 'name-desc']

export interface Display extends NumberStyle {
  thresholds?: Threshold[]
  threshold_mode?: 'value' | 'percent'
  mappings?: Mapping[]
  unit?: string
  sort?: Sort
  limit?: number
  hide_zero?: boolean
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
    case 'series':
      return d.unit != null ? { ...w, unit: d.unit } : w
    case 'list': {
      let items = w.items.map((i) => {
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

function sortRows<T>(rows: T[], sort: Sort | undefined, value: (r: T) => number | null, name: (r: T) => string): T[] {
  if (!sort) return rows
  const dir = sort.endsWith('asc') ? 1 : -1
  const out = [...rows]
  if (sort.startsWith('name')) out.sort((a, b) => dir * name(a).localeCompare(name(b), undefined, { numeric: true }))
  else out.sort((a, b) => dir * ((value(a) ?? -Infinity) - (value(b) ?? -Infinity)))
  return out
}

/** Which display settings mean something for this data: numbers to format and colour, rows to
 *  sort and cut. */
export function displaysFor(w: Widget): { numbers: boolean; colours: boolean; rows: boolean } {
  const numbers = (w.type === 'stat' && typeof w.value === 'number') || w.type === 'sparkline' || w.type === 'series'
    || (w.type === 'list' && w.items.some((i) => i.number != null)) || numberColumns(w).length > 0
  return { numbers, colours: numbers, rows: w.type === 'list' || w.type === 'status' || w.type === 'table' }
}
