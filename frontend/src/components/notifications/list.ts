import type { NotificationItem } from '@bitsandbricks/ui'
import type { Problem, ProblemList } from '@/api/types'
import { ago } from '@/lib/time'

/** Which part of the bell a notification belongs to: down, a warning, or seat and port trouble. */
export type NotifyGroup = 'down' | 'warn' | 'seats'
export const GROUPS: NotifyGroup[] = ['down', 'warn', 'seats']

/** Everything the bell counts, worst first: down, then warnings (newest first in each), then seat
 *  and port trouble as the server sorts it. Muted ones are left out, as the bell's count does.
 *  The search also looks at the device and the seat, which the row doesn't show. */
export function notifyItems(data: ProblemList | undefined): NotificationItem[] {
  if (!data) return []
  const live = data.problems.filter((p) => !p.muted)
  const newest = (a: Problem, b: Problem) => (b.since ?? 0) - (a.since ?? 0)
  const item = (p: Problem, group: NotifyGroup): NotificationItem => ({
    id: p.id, state: p.level, title: p.title, where: p.where, group,
    time: p.since ? ago(p.since) : undefined,
    search: [p.title, p.where, p.device, p.seat].filter(Boolean).join(' '),
  })
  return [
    ...live.filter((p) => p.level === 'down').sort(newest).map((p) => item(p, 'down')),
    ...live.filter((p) => p.level !== 'down').sort(newest).map((p) => item(p, 'warn')),
    ...(data.attention ?? []).filter((p) => !p.muted).map((p) => item(p, 'seats')),
  ]
}
