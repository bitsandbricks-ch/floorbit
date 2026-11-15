import type { Incident } from '@/api/types'

export const WAITING_AFTER = 10 * 60

/** Open, nobody on it, and opened at least WAITING_AFTER ago (issue #296). */
export function isWaiting(i: Pick<Incident, 'status' | 'assignee' | 'created_at'>, now: number) {
  return i.status === 'open' && !i.assignee && now - i.created_at >= WAITING_AFTER
}

/** The open column: waiting incidents on top, longest first, so the oldest job isn't at the bottom (issue #300). */
export function openOrder<T extends Pick<Incident, 'status' | 'assignee' | 'created_at'>>(items: T[], now: number): T[] {
  const waiting = items.filter((i) => isWaiting(i, now)).sort((a, b) => a.created_at - b.created_at)
  return [...waiting, ...items.filter((i) => !isWaiting(i, now))]
}

/** What "Take the next one" takes: the oldest open incident nobody has that this account may work (issue #306). */
export function nextToTake<T extends Pick<Incident, 'status' | 'assignee' | 'created_at' | 'can_work'>>(items: T[]): T | undefined {
  return items.filter((i) => i.status === 'open' && !i.assignee && i.can_work).sort((a, b) => a.created_at - b.created_at)[0]
}

/** "Waiting 25 min", or with hours once it has waited an hour. */
export function waitedFor(seconds: number, t: (k: string, o?: Record<string, unknown>) => string) {
  const mins = Math.floor(seconds / 60)
  return mins < 60 ? t('incidents.waiting', { count: mins }) : t('incidents.waitingLong', { h: Math.floor(mins / 60), m: mins % 60 })
}
