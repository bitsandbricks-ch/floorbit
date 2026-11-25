import { useBrowserNotify } from '@bitsandbricks/ui'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { useLiveEvents } from '@/api/live'
import { useMe } from '@/api/queries'
import { crewNotify, watchedSeats } from './crewNotify'

const EVENTS = 'incident.changed incident.dispatched switch.status health.changed seats.changed'

type Incident = { id: string; seat?: string | null; switch?: string | null; title?: string }
type Change = { id: string; name?: string; status?: string; previous?: string; summary?: string }

// A mute means "stop paging me about this" (issue #282). If the list can't be read, notify anyway.
async function muted(key: string) {
  try {
    return ((await get<{ mutes?: { switch_id: string }[] }>('/api/problems')).mutes ?? []).some((m) => m.switch_id === key)
  } catch {
    return false
  }
}

/** Browser notifications for the crew (issue #154): listens to the live events while they are on
 *  for this browser and the browser allows them. Only while a Floorbit tab is open (no push service). */
export function CrewNotify() {
  const { prefs, permission } = useBrowserNotify(crewNotify)
  // No stream of its own while off: the pages open one only when they need it.
  return prefs.on && permission === 'granted' ? <Listener /> : null
}

function Listener() {
  const { t } = useTranslation()
  const me = useMe().data?.user?.username ?? null

  async function incident(id: string) {
    if (crewNotify.prefs().kinds.incidents === false || crewNotify.quietNow()) return
    let item: Incident | undefined
    try {
      item = (await get<{ incidents?: Incident[] }>('/api/incidents')).incidents?.find((i) => i.id === id)
    } catch {
      return   // no incident board for this account
    }
    if (!item) return
    const where = item.seat ? t('crewNotify.seat', { seat: item.seat }) : item.switch ? t('crewNotify.switch', { name: item.switch }) : ''
    crewNotify.notify('incidents', t('crewNotify.incident'), { body: [where, item.title].filter(Boolean).join(': '), tag: `incident-${item.id}`, url: '/incidents' })
  }

  async function switchDown(data: Record<string, unknown>) {
    if (crewNotify.prefs().kinds.switches === false || crewNotify.quietNow()) return
    if (data.id && await muted(String(data.id))) return
    const name = typeof data.name === 'string' ? data.name : 'Switch'
    crewNotify.notify('switches', t('crewNotify.down'), { body: t('crewNotify.downText', { name }), tag: `switch-${String(data.id ?? name)}`, url: '/' })
  }

  // The health wall only sends confirmed changes, so a blip doesn't notify (issue #282).
  async function servicesDown(changes: Change[]) {
    if (crewNotify.prefs().kinds.services === false || crewNotify.quietNow()) return
    for (const c of changes) {
      if (c.status !== 'down' || c.previous === 'down' || await muted(`health:${c.id}`)) continue
      crewNotify.notify('services', t('crewNotify.service'), { body: [c.name, c.summary].filter(Boolean).join(': '), tag: `health-${c.id}`, url: '/health' })
    }
  }

  // Watched seats (issue #178): like a job sent to me, they come through quiet hours unless that is off.
  function seats(list: unknown) {
    const watch = watchedSeats()
    if (!watch.length || !Array.isArray(list)) return
    for (const entry of list) {
      if (!Array.isArray(entry)) continue
      const [seat, on] = entry as [string, number]
      if (!watch.includes(seat)) continue
      crewNotify.notify('seats', t('crewNotify.watched'), {
        body: t(on ? 'crewNotify.seatUp' : 'crewNotify.seatDown', { seat }), tag: `seat-${seat}`,
        url: `/plan?seat=${encodeURIComponent(seat)}`, urgent: true,
      })
    }
  }
  useLiveEvents(EVENTS, (raw, type) => {
    const data = (raw ?? {}) as Record<string, unknown>
    if (type === 'incident.dispatched') {
      if (me && data.assignee === me) crewNotify.notify('jobs', t('crewNotify.job'), { body: t('crewNotify.jobText'), tag: `job-${String(data.id)}`, url: '/jobs', urgent: true })
    } else if (type === 'incident.changed') {
      if (data.action === 'created' && data.id) void incident(String(data.id))
    } else if (type === 'switch.status') {
      if (data.status === 'offline') void switchDown(data)
    } else if (type === 'health.changed') {
      if (Array.isArray(data.changes)) void servicesDown(data.changes as Change[])
    } else if (type === 'seats.changed') {
      seats(data.seats)
    }
  })

  return null
}
