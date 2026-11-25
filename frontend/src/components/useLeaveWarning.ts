import { useEffect, useSyncExternalStore } from 'react'

/** Where a page may go without losing its changes: the same page by default. */
export type Keep = (pathname: string) => boolean

const guards = new Set<{ keep: Keep }>()
const listeners = new Set<() => void>()
const tell = () => listeners.forEach((l) => l())

/** Is anything unsaved that a move to ``pathname`` would lose? (LeaveGuard asks before a link.) */
export function wouldLose(pathname: string): boolean {
  for (const g of guards) if (!g.keep(pathname)) return true
  return false
}

export function useGuarded(): boolean {
  return useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l) } }, () => guards.size > 0)
}

/** While something is unsaved, closing or reloading the tab asks first (the browser's own question),
 *  and so does a link inside the app that leaves the page (LeaveGuard, #993). ``keep``: the
 *  addresses that keep the changes (Settings keeps them across its entries). */
export function useLeaveWarning(unsaved: boolean, keep?: Keep) {
  useEffect(() => {
    if (!unsaved) return
    const here = window.location.pathname
    const guard = { keep: keep ?? ((p: string) => p === here) }
    guards.add(guard)
    tell()
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => {
      guards.delete(guard)
      tell()
      window.removeEventListener('beforeunload', warn)
    }
    // ``keep`` is a rule the caller writes inline; a new function each render is the same rule.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unsaved])
}
