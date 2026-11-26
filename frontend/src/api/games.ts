import type { CacheRow, LancacheData } from './lancache'

export interface LauncherRow {
  id: string
  name: string
  kind: 'game' | 'launcher' | 'sitegroup'
  part_of: string | null
  category: string
  lookups: number | null
  dns_seats_max: number | null
  traffic_bytes: number | null
  traffic_seats: number | null
  cache_hit_bytes: number | null
  cache_miss_bytes: number | null
  players: number | null
  seats: number
}
export interface GamesData {
  launchers: LauncherRow[]
  titles: LauncherRow[]
  sitegroups: LauncherRow[]
  games: { name: string; bytes: number; seats: number }[]
  other_caches: CacheRow[]
  cache: LancacheData
  sources: { dns: boolean; traffic: boolean; cache: boolean; servers: boolean }
  min_seats: { dns: number; traffic: number | null }
}
