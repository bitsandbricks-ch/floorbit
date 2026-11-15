import type { NavPage } from './sections'

/** What the server puts into every crew page for the sidebar (templates/_nav.html), so it draws
 *  at once, without waiting for an API call. */
export interface NavBoot {
  pages: NavPage[]
  brand: { logo: string | null; name: string | null }
  user: { name: string; username: string } | null
  /** Sign-in is on: offer "Sign out". */
  signOut: boolean
}

const EMPTY: NavBoot = { pages: [], brand: { logo: null, name: null }, user: null, signOut: false }

export function readBoot(): NavBoot {
  const el = typeof document === 'undefined' ? null : document.getElementById('fb-nav-data')
  if (!el?.textContent) return EMPTY
  try {
    return { ...EMPTY, ...(JSON.parse(el.textContent) as Partial<NavBoot>) }
  } catch {
    return EMPTY
  }
}

// Folded to icons or open: a cookie, so the server reserves the right width before any script runs.
const COOKIE = 'floorbit_nav'

export function readRail(): boolean {
  return typeof document !== 'undefined' && document.cookie.split('; ').includes(`${COOKIE}=rail`)
}

export function saveRail(rail: boolean) {
  document.cookie = `${COOKIE}=${rail ? 'rail' : 'full'}; path=/; max-age=31536000; samesite=lax`
  document.documentElement.dataset.nav = rail ? 'rail' : 'full'
}

const OPEN_KEY = 'floorbit-nav-open'

/** The sections someone opened, on this browser. */
export function readOpen(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(OPEN_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

export function saveOpen(ids: string[]) {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify(ids))
  } catch {
    /* private mode: open sections last for this visit */
  }
}
