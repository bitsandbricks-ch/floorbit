// The value of a date-and-time field, as the browser's datetime-local input had it:
// "YYYY-MM-DDTHH:MM" in local time, so the pages that used that input don't change.
// From Seatbit's date-time-picker (by Mike).

export type Parts = { y: number; m: number; d: number; hh: number; mm: number }

const pad = (n: number) => String(n).padStart(2, '0')

export function parseValue(v: string): Parts | null {
  const r = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(v)
  return r ? { y: +r[1], m: +r[2] - 1, d: +r[3], hh: +r[4], mm: +r[5] } : null
}

export const toValue = (p: Parts) => `${p.y}-${pad(p.m + 1)}-${pad(p.d)}T${pad(p.hh)}:${pad(p.mm)}`

/** "14.11.2026 18:00": the text to edit. */
export function editText(v: string): string {
  const p = parseValue(v)
  return p ? `${pad(p.d)}.${pad(p.m + 1)}.${p.y} ${pad(p.hh)}:${pad(p.mm)}` : ''
}

/** Reads what people type or paste: "14.11.2026 18:00", "14.11.26 18", "14.11. 1800",
 *  "14/11/2026 18.30" or "2026-11-14T18:00". A missing year means the next such date; a missing
 *  time uses ``fallback``. Day before month, as in Switzerland. */
export function parseTyped(text: string, fallback: { hh: number; mm: number }, now = new Date()): Parts | null {
  const t = text.trim()
  if (!t) return null
  const iso = parseValue(t)
  if (iso) return iso
  const m = /(\d{1,2})[./-](\d{1,2})[./-]?(\d{2,4})?\s*,?\s*(?:(\d{1,2})(?:[:.h]?(\d{2}))?)?\s*$/.exec(t)
  if (!m) return null
  const d = +m[1]
  const mo = +m[2] - 1
  let y = m[3] ? +m[3] : now.getFullYear()
  if (m[3] && m[3].length === 2) y += 2000
  const hh = m[4] !== undefined ? +m[4] : fallback.hh
  const mm = m[5] !== undefined ? +m[5] : m[4] !== undefined ? 0 : fallback.mm
  if (mo < 0 || mo > 11 || hh > 23 || mm > 59) return null
  const date = new Date(y, mo, d)
  if (date.getMonth() !== mo) return null   // 31.02.
  if (!m[3] && date < new Date(now.getFullYear(), now.getMonth(), now.getDate())) y += 1
  return { y, m: mo, d, hh, mm }
}
