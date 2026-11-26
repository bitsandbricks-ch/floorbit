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
  const [folded, setState] = useState<string[]>(load)
  const save = (next: string[]) => {
    setState(next)
    try { localStorage.setItem(KEY, JSON.stringify(next.slice(-200))) } catch { /* private window: this visit only */ }
  }
  const isFolded = (key: string) => folded.includes(key)
  const setAll = (keys: string[], fold: boolean) =>
    save(fold ? [...new Set([...folded, ...keys])] : folded.filter((k) => !keys.includes(k)))
  /** The groups of `scope` (the page on screen) that are folded now: the rest of `scope` unfolds,
   *  other pages' groups stay as they were. */
  const setFolded = (scope: string[], keys: string[]) => save([...folded.filter((k) => !scope.includes(k)), ...keys])
  return { isFolded, setAll, setFolded }
}
