// Which firewall an IP address or a seat goes through (GET /api/firewalls/lookup, Mike 2026-11-24).
import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { FirewallRouteState } from '@/api/types'

export type FirewallLookup = {
  query: string; kind: 'ip' | 'seat'; seat: string | null; found: boolean
  intended?: string; now?: string | null; state?: FirewallRouteState; range?: string; range_id?: string
  fallback?: string[]
  /** The range and the part the address is in; left out for a seat without seats.view. */
  cidr?: string; part?: string
}

export function useFirewallLookup(q: string) {
  return useQuery({
    queryKey: qk.firewallLookup(q),
    queryFn: () => get<FirewallLookup>(`/api/firewalls/lookup?q=${encodeURIComponent(q)}`),
    enabled: q.trim() !== '',
    retry: false,
  })
}
