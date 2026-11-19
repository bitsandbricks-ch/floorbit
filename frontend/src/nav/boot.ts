import { useSyncExternalStore } from 'react'
import { FOLDED, type CustomSection, type NavPage } from './sections'

/** What the server puts into every crew page for the sidebar (templates/_nav.html), so it draws
 *  at once, without waiting for an API call. */
export interface NavBoot {
  pages: NavPage[]
  /** The sections admins made, with only the links this account may open (floorbit/nav_sections.py). */
  custom?: CustomSection[]
  brand: { logo: string | null; name: string | null }
  /** ``platform``: an admin of the platform visiting this tenant, with no account of their own here. */
  user: { name: string; username: string; platform?: boolean } | null
  /** Sign-in is on: offer "Sign out". */
  signOut: boolean
  /** The platform has more than one tenant: the tenant switcher asks for the person's other ones. */
  tenants?: boolean
  /** The signed-in account's sidebar settings; null without sign-in (the browser keeps them). */
  prefs: NavPrefs | null
}

/** Favourite pages first in the sidebar. ``accordion`` is kept for accounts that saved it; the
 *  grouped sidebar no longer folds the other groups. */
export interface NavPrefs { favourites: string[]; accordion: boolean }

const EMPTY: NavBoot = { pages: [], custom: [], brand: { logo: null, name: null }, user: null, signOut: false, prefs: null }
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

// One copy of the sidebar settings for the whole page, so a page's own "Pin" button and the
// sidebar's stars change the same list and both show it at once.
let shared: NavPrefs | null = null
const listeners = new Set<() => void>()

/** The sidebar settings and a way to change (and save) them. */
export function useNavPrefs(boot: NavBoot): [NavPrefs, (next: NavPrefs) => void] {
  shared ??= readPrefs(boot)
  const prefs = useSyncExternalStore(
    (l) => { listeners.add(l); return () => { listeners.delete(l) } },
    () => shared ?? DEFAULT_PREFS,
    () => shared ?? DEFAULT_PREFS,
  )
  const set = (next: NavPrefs) => {
    shared = next
    savePrefs(boot, next)
    listeners.forEach((l) => l())
  }
  return [prefs, set]
}

/** Tests: forget the settings read so far. */
export function resetNavPrefs() {
  shared = null
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

const FOLDED_KEY = 'floorbit-nav-folded'

/** The groups someone folded, on this browser; groups in FOLDED start folded. */
export function readFolded(): string[] {
  try {
    const raw = localStorage.getItem(FOLDED_KEY)
    if (raw === null) return [...FOLDED]
    const v: unknown = JSON.parse(raw)
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [...FOLDED]
  } catch {
    return [...FOLDED]
  }
}

export function saveFolded(ids: string[]) {
  try {
    localStorage.setItem(FOLDED_KEY, JSON.stringify(ids))
  } catch {
    /* private mode: folded groups last for this visit */
  }
}

/** Another tenant of the platform the signed-in person can switch to: with their linked account
 *  there, or as a platform admin (floorbit/tenant_switch.py). */
export interface OtherTenant { id: string; name: string; url: string; how: 'account' | 'platform' }

/** The person's other tenants; none when that can't be asked. */
export async function fetchOtherTenants(): Promise<OtherTenant[]> {
  try {
    const res = await fetch('/api/tenant/mine', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    if (!res.ok) return []
    const body = (await res.json()) as { tenants?: OtherTenant[] }
    return Array.isArray(body.tenants) ? body.tenants.filter((t) => t.url) : []
  } catch {
    return []
  }
}

/** Where to send the browser to arrive signed in at that tenant; throws with the server's text. */
export async function switchTenant(id: string): Promise<string> {
  const res = await fetch('/api/tenant/switch', {
    method: 'POST', credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenant: id }),
  })
  const body = (await res.json().catch(() => ({}))) as { url?: string; error?: string }
  if (!res.ok || !body.url) throw new Error(body.error || res.statusText)
  return body.url
}
