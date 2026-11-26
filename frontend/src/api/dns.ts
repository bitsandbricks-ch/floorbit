export type DnsCategory = 'gaming' | 'streaming' | 'social' | 'updates' | 'other'
export interface DnsSite {
  site: string
  category: DnsCategory
  lookups: number
  blocked: number
  clients_max: number
  first_seen?: number
}
export interface DnsData {
  hours: { t: number; lookups: number; blocked: number }[]
  lookups: number
  blocked: number
  block_share: number | null
  sites: DnsSite[]
  /** How many sites are named; `sites` holds the busiest of them. */
  named: number
  categories: { id: DnsCategory; lookups: number }[]
  unnamed_lookups: number
  new: DnsSite[]
  blocked_sites: DnsSite[]
  min_clients: number
  plugins: number
  last_poll: number | null
  error: string | null
}
