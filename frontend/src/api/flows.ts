// Traffic insights from NetFlow/IPFIX (floorbit/flows).
export type FlowCategory = 'gaming' | 'streaming' | 'downloads' | 'updates' | 'web' | 'other'
export type FlowMix = Partial<Record<FlowCategory, number>>
export interface FlowAnomaly {
  id: string
  kind: 'p2p' | 'burst' | 'rogue-dhcp' | 'rogue-dns'
  seat: string | null
  area: string | null
  title: string
  detail: string
  first_seen: number
  last_seen: number
}
/** A service on the Traffic page: down (to the seats) and up, bytes per hour (unix hour start as text)
 *  and per seat block. An older agent sends only name, category, bytes and seats. */
export interface FlowService {
  name: string
  category: FlowCategory
  bytes: number
  seats: number
  down?: number
  up?: number
  trend?: Record<string, number>
  areas?: Record<string, number>
}

export interface FlowsData {
  collector: boolean
  can_see_seats: boolean
  rules_error: string | null
  demo?: boolean
  stale?: boolean
  /** The local agent whose collector sent this summary (issue #2). */
  agent?: string
  updated?: number
  flows?: number
  exporters?: { address: string; flows: number; last: number | null }[]
  mix_hour?: FlowMix
  mix_day?: FlowMix
  series?: ({ t: number } & FlowMix)[]
  areas?: { area: string; bytes: number; mix: FlowMix }[]
  services?: FlowService[]
  other_services?: number
  seats?: { seat: string; area: string | null; bytes: number; mix: FlowMix }[] | null
  anomalies?: FlowAnomaly[]
  min_seats?: number
  retention_days?: number
  raw?: { files: number; bytes: number; oldest: string | null }
}
