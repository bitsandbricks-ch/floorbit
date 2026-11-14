import type { ReportHour } from '@/api/types'

/** 1 h 05 min, like the PDF (floorbit/report_pdf.py). */
export function duration(seconds: number | null | undefined): string {
  const s = Math.round(seconds ?? 0)
  if (s < 60) return `${s} s`
  const minutes = Math.floor(s / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours} h ${String(minutes % 60).padStart(2, '0')} min`
  return `${Math.floor(hours / 24)} d ${hours % 24} h`
}

export function bytes(value: number): string {
  for (const [unit, step] of [['TB', 1e12], ['GB', 1e9], ['MB', 1e6]] as const) {
    if (value >= step) return `${(value / step).toFixed(1)} ${unit}`
  }
  return `${Math.round(value / 1e3)} kB`
}

export function stamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** An SVG path through one value per hour, in a w×h box with `top` at the top. */
export function hourPath(hours: ReportHour[], key: 'online_max' | 'checked_in' | 'avg_bps', top: number, w: number, h: number): string {
  if (hours.length < 2) return ''
  const start = hours[0].t
  const span = hours[hours.length - 1].t + 3600 - start
  return hours
    .map((row, i) => `${i ? 'L' : 'M'}${(((row.t + 1800 - start) / span) * w).toFixed(1)},${(h - (row[key] / Math.max(1, top)) * h).toFixed(1)}`)
    .join(' ')
}

/** The PDF link: the page's language and the reader's time zone. */
export function pdfUrl(lang: string, people: boolean, tzOffset: number): string {
  const q = new URLSearchParams({ lang: lang.startsWith('de') ? 'de' : 'en', tz: String(tzOffset) })
  if (people) q.set('people', '1')
  return `/api/report.pdf?${q}`
}
