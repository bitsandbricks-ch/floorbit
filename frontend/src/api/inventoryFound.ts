import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { useUnknownSenders } from './unknownSenders'

/** A box the switches see by LLDP or CDP that matches no inventory device (issue #891). */
export interface FoundDevice {
  name: string
  protocol: string
  seen_by: { switch: string; port: string; remote_port: string }[]
}
/** A link LLDP or CDP sees between two inventory devices that no planned link explains. */
export interface FoundLink {
  key: string; a: string; a_port: string; b: string; b_port: string; protocol: string; speed: number | null
}
export interface FoundList { devices: FoundDevice[]; links: FoundLink[]; ignored: { devices: number; links: number } }

/** Under the inventory's key, so anything that changes the inventory asks again. */
export const foundKey = ['inventory', 'found'] as const

export function useFound() {
  return useQuery({ queryKey: foundKey, queryFn: () => get<FoundList>('/api/inventory/found'), refetchInterval: 120_000 })
}

/** What Inventory › Discovery's tab counts: found devices and links, and unknown senders. */
export function useFoundCount() {
  const found = useFound().data
  const senders = useUnknownSenders().data
  return (found?.devices.length ?? 0) + (found?.links.length ?? 0) + (senders?.senders.filter((s) => !s.ignored).length ?? 0)
}
