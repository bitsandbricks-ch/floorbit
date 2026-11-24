import type { Problem, ProblemList } from '@/api/types'

/** The handbook's page size for long lists. */
export const PER_PAGE = 50

/** Which part of the bell a notification belongs to: down, a warning, or seat and port trouble. */
export type NotifyGroup = 'down' | 'warn' | 'seats'
export type NotifyFilter = 'all' | NotifyGroup
export interface NotifyItem { p: Problem; group: NotifyGroup }

/** Everything the bell counts, worst first: down, then warnings (newest first in each), then seat
 *  and port trouble as the server sorts it. Muted ones are left out, as the bell's count does. */
export function notifyItems(data: ProblemList | undefined): NotifyItem[] {
  if (!data) return []
  const live = data.problems.filter((p) => !p.muted)
  const newest = (a: Problem, b: Problem) => (b.since ?? 0) - (a.since ?? 0)
  return [
    ...live.filter((p) => p.level === 'down').sort(newest).map((p) => ({ p, group: 'down' as const })),
    ...live.filter((p) => p.level !== 'down').sort(newest).map((p) => ({ p, group: 'warn' as const })),
    ...(data.attention ?? []).filter((p) => !p.muted).map((p) => ({ p, group: 'seats' as const })),
  ]
}

export function countGroups(items: NotifyItem[]): Record<NotifyFilter, number> {
  const c = { all: items.length, down: 0, warn: 0, seats: 0 }
  for (const it of items) c[it.group] += 1
  return c
}

/** The items a filter and a search leave; the search looks at title, place, device and seat. */
export function filterItems(items: NotifyItem[], filter: NotifyFilter, search: string): NotifyItem[] {
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return items.filter(({ p, group }) => {
    if (filter !== 'all' && group !== filter) return false
    if (!words.length) return true
    const text = [p.title, p.where, p.device, p.seat].filter(Boolean).join(' ').toLowerCase()
    return words.every((w) => text.includes(w))
  })
}

/** The page (from 1) that shows the item at `index`. */
export const pageOf = (index: number) => Math.floor(index / PER_PAGE) + 1
