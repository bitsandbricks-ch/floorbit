import { useSyncExternalStore } from 'react'

// The title of the page on screen, for the top bar's breadcrumbs: Layout sets it, so a sub page
// (one agent, one device) shows its own name after its parent's.
let title = ''
const listeners = new Set<() => void>()

export function setPageTitle(next: string) {
  if (next === title) return
  title = next
  listeners.forEach((l) => l())
}

export function usePageTitle(): string {
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => { listeners.delete(l) } },
    () => title,
    () => title,
  )
}
