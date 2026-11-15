/** Lower case without accents, so "ubergabe" finds "Übergabe". */
export function fold(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

const RECENT_KEY = 'floorbit-recent-pages'
export const RECENT_MAX = 5
// More are kept than shown: pages that are not in the list (a closed feature, a detail page) drop out.
const RECENT_KEPT = 10

/** The pages opened last on this browser, newest first (issue #244). */
export function recentPages(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, RECENT_KEPT) : []
  } catch {
    return []
  }
}

export function rememberPage(path: string) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([path, ...recentPages().filter((p) => p !== path)].slice(0, RECENT_KEPT)))
  } catch {
    /* private mode: no history, the list keeps its usual order */
  }
}
