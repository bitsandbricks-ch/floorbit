import { useSyncExternalStore } from 'react'

/** How the editor snaps, and whether it shows rulers: the crew's own choice, kept in this browser. */
export interface SnapPrefs {
  /** Moves, draws and wall corners land on the grid (Alt still leaves it). */
  grid: boolean
  /** Moves line up with other items' edges and middles, wall corners land on other walls'. */
  items: boolean
  rulers: boolean
}

const KEY = 'floorbit-plan-snap'
const DEFAULTS: SnapPrefs = { grid: true, items: true, rulers: true }
const listeners = new Set<() => void>()
let current: SnapPrefs = read()

function read(): SnapPrefs {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Partial<SnapPrefs> | null
    if (!raw || typeof raw !== 'object') return DEFAULTS
    return { grid: raw.grid !== false, items: raw.items !== false, rulers: raw.rulers !== false }
  } catch {
    return DEFAULTS
  }
}

export function setSnapPrefs(next: Partial<SnapPrefs>) {
  current = { ...current, ...next }
  try { localStorage.setItem(KEY, JSON.stringify(current)) } catch { /* private window: this visit only */ }
  listeners.forEach((l) => l())
}

/** The snap settings, shared by the top bar's toggles and the editor. */
export function useSnapPrefs(): SnapPrefs {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l) }, () => current)
}

/** For tests: back to the defaults. */
export function resetSnapPrefs() {
  current = DEFAULTS
  try { localStorage.removeItem(KEY) } catch { /* nothing kept */ }
  listeners.forEach((l) => l())
}
