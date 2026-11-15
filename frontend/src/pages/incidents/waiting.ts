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

export const UNSEEN_AFTER = 5 * 60

/** Seconds since a job was sent to a tech who hasn't said "On my way", once that is UNSEEN_AFTER or more
 * (issue #364): their phone may be in a pocket, and a lead can send it to someone else. Otherwise null. */
export function unseenFor(i: Pick<Incident, 'status' | 'assignee' | 'dispatched_at' | 'taken_at'>, now: number): number | null {
  if (!i.assignee || !i.dispatched_at || i.taken_at || i.status === 'fixed') return null
  const s = now - i.dispatched_at
  return s >= UNSEEN_AFTER ? s : null
}

/** "Waiting 25 min", or with hours once it has waited an hour. */
export function waitedFor(seconds: number, t: (k: string, o?: Record<string, unknown>) => string) {
  const mins = Math.floor(seconds / 60)
  return mins < 60 ? t('incidents.waiting', { count: mins }) : t('incidents.waitingLong', { h: Math.floor(mins / 60), m: mins % 60 })
}

/** How long an incident took from filed to fixed (issue #332), e.g. "fixed after 1 h 5 min".
 * ``alone`` starts the sentence, for a card with nobody named on it. */
export function fixedAfter(seconds: number, t: (k: string, o?: Record<string, unknown>) => string, alone = false) {
  const mins = Math.max(0, Math.round(seconds / 60))
  const key = alone ? 'incidents.fixedAfterAlone' : 'incidents.fixedAfter'
  return mins < 1 ? t(`${key}Now`) : mins < 60 ? t(key, { count: mins }) : t(`${key}Long`, { h: Math.floor(mins / 60), m: mins % 60 })
}
