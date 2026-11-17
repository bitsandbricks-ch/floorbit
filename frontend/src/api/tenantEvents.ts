// The tenant's events (docs/tenancy.md): which one is live and which one this browser works on.
import { useEffect, useState } from 'react'

export type TenantEventStatus = 'planning' | 'live' | 'closed'
export type TenantEvent = { id: string; name: string; status: TenantEventStatus; created_at?: number }
export type TenantEvents = { events: TenantEvent[]; live: string; current: string }
export type CopyPart = 'halls' | 'seats' | 'inventory' | 'cables' | 'power' | 'services' | 'schedule'
export type CopyChanges = Record<string, { added: number; changed: number; removed: number }>

export const COPY_PARTS: CopyPart[] = ['halls', 'seats', 'inventory', 'cables', 'power', 'services', 'schedule']
export const TENANT_EVENTS_URL = '/api/tenant/events'

/** Work on this event from now on (null: follow the live one), then load the page again: every
 *  part of it, the floor plan too, reads the event's documents. */
export async function pickEvent(id: string | null, then?: string): Promise<void> {
  await fetch('/api/tenant/current', {
    method: 'PUT', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ event: id }),
  })
  // Drop a ?event= that would pick the old one again.
  const url = new URL(then ?? window.location.href, window.location.origin)
  url.searchParams.delete('event')
  window.location.assign(url.pathname + url.search + url.hash)
}

/** The event list, read once per page with plain fetch: the pages Flask draws load only the
 *  sidebar's code, without the query client. */
export function useTenantEvents(): TenantEvents | null {
  const [data, setData] = useState<TenantEvents | null>(null)
  useEffect(() => {
    let stop = false
    fetch(TENANT_EVENTS_URL + window.location.search, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? (r.json() as Promise<TenantEvents>) : null))
      .then((d) => { if (!stop) setData(d) })
      .catch(() => { /* no banner without an answer */ })
    return () => { stop = true }
  }, [])
  return data
}
