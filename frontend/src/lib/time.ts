import i18next from 'i18next'

/** Times as every page writes them, in the language the sidebar picked. One copy, so "5 minutes ago"
 *  reads the same on Problems, Incidents and the check-ins. */

/** "5 minutes ago", "yesterday"; "–" for no time. */
export function ago(ts: number | null | undefined, lang = i18next.language, now = Date.now()): string {
  if (!ts) return '–'
  const s = Math.max(0, now / 1000 - ts)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  if (s < 45) return rtf.format(0, 'second')
  if (s < 3600) return rtf.format(-Math.max(1, Math.round(s / 60)), 'minute')
  if (s < 86400) return rtf.format(-Math.round(s / 3600), 'hour')
  return rtf.format(-Math.round(s / 86400), 'day')
}

/** "14:05" (or "2:05 PM"). */
export function clock(ts: number, lang = i18next.language): string {
  return new Date(ts * 1000).toLocaleTimeString(lang || [], { hour: '2-digit', minute: '2-digit' })
}

/** "Sat 14:05", for times that may be on another day of the event. */
export function dayClock(ts: number, lang = i18next.language): string {
  return new Date(ts * 1000).toLocaleString(lang || [], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
}
