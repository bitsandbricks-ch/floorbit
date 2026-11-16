import type { NavPage } from './sections'

/** What the server puts into every crew page for the sidebar (templates/_nav.html), so it draws
 *  at once, without waiting for an API call. */
export interface NavBoot {
  pages: NavPage[]
  brand: { logo: string | null; name: string | null }
  user: { name: string; username: string } | null
  /** Sign-in is on: offer "Sign out". */
  signOut: boolean
  /** The signed-in account's sidebar settings; null without sign-in (the browser keeps them). */
  prefs: NavPrefs | null
}

/** Favourite pages first in the sidebar, and whether opening a section folds the others. */
export interface NavPrefs { favourites: string[]; accordion: boolean }

const EMPTY: NavBoot = { pages: [], brand: { logo: null, name: null }, user: null, signOut: false, prefs: null }
const PREFS_KEY = 'floorbit-nav-prefs'
export const DEFAULT_PREFS: NavPrefs = { favourites: [], accordion: true }

function cleanPrefs(v: unknown): NavPrefs {
  const o = (v && typeof v === 'object' ? v : {}) as Partial<NavPrefs>
  const favourites = Array.isArray(o.favourites) ? o.favourites.filter((x): x is string => typeof x === 'string') : []
  return { favourites, accordion: o.accordion !== false }
}

/** The account's settings, or this browser's when nobody is signed in. */
export function readPrefs(boot: NavBoot): NavPrefs {
  if (boot.prefs) return cleanPrefs(boot.prefs)
  try {
    return cleanPrefs(JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null'))
  } catch {
    return DEFAULT_PREFS
  }
}

export function savePrefs(boot: NavBoot, prefs: NavPrefs) {
  if (boot.prefs) {
    // With the account, so they follow the person to every browser. A failed save keeps them for this visit.
    void fetch('/api/auth/me/nav', {
      method: 'PUT', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(prefs),
    }).catch(() => undefined)
    return
  }
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* private mode: they last for this visit */
  }
}

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
