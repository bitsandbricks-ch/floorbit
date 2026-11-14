import { useSyncExternalStore } from 'react'

// static/js/theme.js owns light/dark (saved choice, OS setting, a preset's lock) and sets
// data-theme on <html> before the first paint. React follows it rather than keeping its own.
declare global {
  interface Window {
    floorTheme?: { current: () => 'light' | 'dark'; toggle: () => 'light' | 'dark' }
  }
}

export type Scheme = 'light' | 'dark'

export function currentScheme(): Scheme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

function subscribe(onChange: () => void) {
  document.addEventListener('themechange', onChange)
  return () => document.removeEventListener('themechange', onChange)
}

export function useScheme(): Scheme {
  return useSyncExternalStore(subscribe, currentScheme)
}

/** Null when the preset fixes the scheme (kiosk, classic): then there is nothing to toggle. */
export function toggleScheme(): (() => void) | null {
  if (document.documentElement.dataset.themeLock || !window.floorTheme) return null
  return () => window.floorTheme?.toggle()
}
