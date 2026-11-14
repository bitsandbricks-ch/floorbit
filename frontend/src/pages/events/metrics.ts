import type { EventFigures } from '@/api/types'
import { bytes, duration } from '../report/format'
import { bps } from '../stats/format'

export type Metric = { key: keyof EventFigures; format: (v: number) => string; better: 'more' | 'less' | null }

/** The rows of the comparison, in the order the events page shows them. */
export const METRICS: Metric[] = [
  { key: 'online_max', format: String, better: null },
  { key: 'checked_in_max', format: String, better: null },
  { key: 'peak_bps', format: (v) => bps(v), better: null },
  { key: 'bytes_moved', format: bytes, better: null },
  { key: 'incidents', format: String, better: 'less' },
  { key: 'median_fix_s', format: duration, better: 'less' },
  { key: 'outages', format: String, better: 'less' },
  { key: 'down_s', format: duration, better: 'less' },
  { key: 'cache_saved_bytes', format: bytes, better: 'more' },
]

/** The value's share of the row's largest, for the bar under each figure. */
export function share(value: number | null, values: (number | null)[]): number {
  const top = Math.max(0, ...values.map((v) => v ?? 0))
  return value && top ? Math.round((value / top) * 100) : 0
}

export function dates(start: number | null, end: number | null): string {
  const day = (ts: number) => new Date(ts * 1000).toLocaleDateString([], { day: '2-digit', month: '2-digit', year: 'numeric' })
  if (!start) return '–'
  const a = day(start)
  const b = end ? day(end) : ''
  return b && b !== a ? `${a} – ${b}` : a
}
