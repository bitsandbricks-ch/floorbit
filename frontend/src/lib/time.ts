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

/** Seconds since the epoch (what the API sends), or a Date. */
export type When = number | Date

/** Every date and time a page shows goes through here. Times are always 24-hour, in English too
 *  (as in Seatbit): an event runs through the night, and "2:05" must not need an AM or PM.
 *  The lint rule in eslint.config.js keeps pages from calling toLocaleTimeString themselves. */
export function formatWhen(when: When, options: Intl.DateTimeFormatOptions, lang = i18next.language): string {
  const d = when instanceof Date ? when : new Date(when * 1000)
  const hasTime = options.hour !== undefined || options.timeStyle !== undefined
  return d.toLocaleString(lang || [], hasTime ? { ...options, hourCycle: 'h23' } : options)
}

/** "14:05". */
export function clock(when: When, lang = i18next.language): string {
  return formatWhen(when, { hour: '2-digit', minute: '2-digit' }, lang)
}

/** "14:05:09", for logs and timelines. */
export function clockSeconds(when: When, lang = i18next.language): string {
  return formatWhen(when, { hour: '2-digit', minute: '2-digit', second: '2-digit' }, lang)
}

/** "Sat 14:05", for times that may be on another day of the event. */
export function dayClock(when: When, lang = i18next.language): string {
  return formatWhen(when, { weekday: 'short', hour: '2-digit', minute: '2-digit' }, lang)
}

/** "16.11.26, 14:05" (with ``seconds``, "14:05:09"). */
export function dateTime(when: When, lang = i18next.language, seconds = false): string {
  return formatWhen(when, { dateStyle: 'short', timeStyle: seconds ? 'medium' : 'short' }, lang)
}

/** "16.11.26", or any other date-only form through ``options``. */
export function dateOnly(when: When, lang = i18next.language,
  options: Intl.DateTimeFormatOptions = { dateStyle: 'short' }): string {
  return formatWhen(when, options, lang)
}
