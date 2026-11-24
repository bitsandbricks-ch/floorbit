// What every crew page shows (the problem count, the crew notice) follows the live events instead
// of asking every 30 s (issue #1414). A read a minute stays as a safety net for what no event
// announces (a mute running out, links, Wi-Fi, plugin problems).
import { useEffect, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { qk } from './keys'
import { useLiveEvent, useLiveEvents } from './live'

/** Events after which the problem list may read differently. */
export const PROBLEM_EVENTS = [
  'alerts.changed', 'attention.changed', 'incident.changed', 'power.changed', 'power.alert',
  'health.changed', 'security.finding', 'forecast.alert', 'logs.alert', 'agents.changed',
  'monitoring.online', 'monitoring.offline', 'cables.changed',
] as const

/** The safety net: the problem list is read at least this often while the page is visible. */
export const PROBLEMS_EVERY_MS = 60_000

/** Several events in a burst (a switch stack going down) cost one read, a second later. */
export const GATHER_MS = 1000

function gathered(run: () => void) {
  let timer: ReturnType<typeof setTimeout> | null = null
  const fn = () => {
    timer ??= setTimeout(() => { timer = null; run() }, GATHER_MS)
  }
  fn.cancel = () => { if (timer) clearTimeout(timer); timer = null }
  return fn
}

/** Call once per page (AppShell and the dashboard screen do): keeps the problem list and the crew notice current. */
export function useLiveRefresh() {
  const qc = useQueryClient()
  const problems = useMemo(() => gathered(() => void qc.invalidateQueries({ queryKey: qk.problems })), [qc])
  useEffect(() => problems.cancel, [problems])
  useEffect(() => {
    // A hidden tab skips it; coming back to the tab reads again anyway (refetchOnWindowFocus).
    const timer = setInterval(() => { if (document.visibilityState !== 'hidden') problems() }, PROBLEMS_EVERY_MS)
    return () => clearInterval(timer)
  }, [problems])
  // The status poll runs every minute; only one that changed a switch changes the list.
  useLiveEvent('monitor.poll', (data) => {
    const changes = (data as { changes?: unknown[] } | null)?.changes
    if (Array.isArray(changes) && changes.length) problems()
  })
  useLiveEvents(PROBLEM_EVENTS.join(' '), problems)
  useLiveEvent('notice.changed', () => void qc.invalidateQueries({ queryKey: qk.notice }))
}
