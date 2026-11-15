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
