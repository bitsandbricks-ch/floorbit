import type { SeatRow } from '@/api/types'

/** The block, switch and source filters above the table (issue #872); empty lets everything through. */
export type SeatFilters = { block?: string | null; switch?: string | null; source?: string | null }

export function matches(row: SeatRow, query: string, onlyManual: boolean, onlyOffPlan = false, f: SeatFilters = {}) {
  if (onlyManual && !row.manual) return false
  if (f.block && (row.block ?? '') !== f.block) return false
  if (f.switch && row.switch !== f.switch) return false
  if (f.source && !row.sources.includes(f.source)) return false
  if (onlyOffPlan && row.on_plan !== false) return false
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [row.seat, `${row.switch} ${row.port}`, row.nick, row.ip, row.mac, row.manual?.note ?? ''].some((v) => v.toLowerCase().includes(q))
}

/** Reads a picked file as text in the browser; the server checks every row. */
export function readText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

/** The distinct non-empty values, in natural order (sw-2 before sw-10), for a filter's choices. */
export const choices = (values: string[]) =>
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
