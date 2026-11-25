import { createBrowserNotify, type NotifyPrefs } from '@bitsandbricks/ui'

const KEY = 'floorbit-notify'
const WATCH_KEY = 'floorbit-watch'

/** This browser's notification settings (the shared BrowserNotify). The kinds are Floorbit's
 *  live events: a job sent to me (urgent: it comes through quiet hours), a new incident, a switch
 *  or a service going down, a watched seat changing (urgent too, like a job). */
export const crewNotify = createBrowserNotify(KEY, '/static/brand/apple-icon.png')

export const KINDS = ['jobs', 'incidents', 'switches', 'services'] as const

interface OldPrefs {
  on?: boolean; incidents?: boolean; jobs?: boolean; switches?: boolean; services?: boolean
  quiet?: boolean; quietFrom?: string; quietTo?: string; jobsInQuiet?: boolean; watch?: string[]
}

/** Settings saved by the old static/js/notify.js had one flag per kind and the watched seats in
 *  the same object: move them to the shared shape once, so nobody's settings are lost. */
export function migrate() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return
    const old = JSON.parse(raw) as OldPrefs & { kinds?: unknown }
    if (old.kinds) return
    if (Array.isArray(old.watch) && !localStorage.getItem(WATCH_KEY)) localStorage.setItem(WATCH_KEY, JSON.stringify(old.watch))
    const kinds: Record<string, boolean> = {}
    for (const k of KINDS) if (old[k] === false) kinds[k] = false
    const next: NotifyPrefs = {
      on: !!old.on, kinds, quiet: !!old.quiet, quietFrom: old.quietFrom ?? '22:00', quietTo: old.quietTo ?? '08:00',
      urgentInQuiet: old.jobsInQuiet !== false,
    }
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage blocked or unreadable: the defaults apply
  }
}

/** The seats this browser watches (issue #178). */
export function watchedSeats(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(WATCH_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

export function setWatchedSeats(seats: string[]) {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(seats.slice(-20))) } catch { /* this visit only */ }
}

// Once per page load, before anything reads the settings.
migrate()
