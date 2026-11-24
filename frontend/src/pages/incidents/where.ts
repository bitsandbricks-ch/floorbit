import type { Incident } from '@/api/types'

type T = (k: string, o?: Record<string, unknown>) => string

/** "Seat A-12", "Circuit B row 1" or "Switch sw-a-01". */
export function whereOf(i: Incident, t: T) {
  return i.seat ? t('incidents.seat', { seat: i.seat })
    : i.circuit_id ? t('incidents.circuit', { name: i.circuit_name ?? i.circuit_id })
      : t('incidents.switch', { name: i.switch_name ?? i.switch_id })
}

/** Where it opens on the floor plan, in its own hall (issue #206), or null for a circuit. */
export function planLinkOf(i: Incident) {
  return i.seat ? `/plan?seat=${encodeURIComponent(i.seat)}`
    : !i.circuit_id && i.switch_name ? `/plan?switch=${encodeURIComponent(i.switch_name)}` : null
}

export const incidentPath = (id: string) => `/incidents/${encodeURIComponent(id)}`

/** "not seen for 7 min", or with hours. */
export function notSeenFor(seconds: number, t: T) {
  const mins = Math.floor(seconds / 60)
  return mins < 60 ? t('incidents.notSeenFor', { count: mins }) : t('incidents.notSeenForLong', { h: Math.floor(mins / 60), m: mins % 60 })
}

/** Whole Mbit/s from 100 on: "912", not "912.4". */
export function mbit(n: number | null) {
  return n == null ? '?' : n >= 100 ? String(Math.round(n)) : String(n)
}
