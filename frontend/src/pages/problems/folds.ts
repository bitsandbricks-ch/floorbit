import { useState } from 'react'

const KEY = 'fb-problems-folded'

function load(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Which groups of the Problems list are folded (issue #1472), remembered in this browser: a crew
 *  member who folds the check-ins keeps them folded across reloads. Keys are "<group by>:<name>". */
export function useFolds() {
  const [folded, setFolded] = useState<string[]>(load)
  const save = (next: string[]) => {
    setFolded(next)
    try { localStorage.setItem(KEY, JSON.stringify(next.slice(-200))) } catch { /* private window: this visit only */ }
  }
  const isFolded = (key: string) => folded.includes(key)
  const toggle = (key: string) => save(isFolded(key) ? folded.filter((k) => k !== key) : [...folded, key])
  const setAll = (keys: string[], fold: boolean) =>
    save(fold ? [...new Set([...folded, ...keys])] : folded.filter((k) => !keys.includes(k)))
  return { isFolded, toggle, setAll }
}
