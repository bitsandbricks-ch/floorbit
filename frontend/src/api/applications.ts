// Applications (docs/applications.md): the games, launchers and site groups Floorbit recognises.
import type { SyncedSource } from './applicationSources'
import { del, post, put } from './client'

export type AppKind = 'game' | 'launcher' | 'sitegroup'
export type AppMatches = { sites: string[]; ports: string[]; cidr: string[]; depots: string[] }
export type AppSeen = {
  lookups: number | null
  dns_seats_max: number | null
  traffic_bytes: number | null
  traffic_seats: number | null
  cache_hit_bytes: number | null
  cache_miss_bytes: number | null
  players: number | null
  seats: number
}
export type Application = AppMatches & {
  id: string
  name: string
  kind: AppKind
  category: string
  part_of: string | null
  caches: string[]
  source: string
  /** Set when a rule source supplied it (``source`` is then ``source:<id>``). */
  source_name?: string
  builtin: boolean
  edited: boolean
  hidden: boolean
  added: AppMatches
  seen: AppSeen
}
export type ApplicationsAnswer = {
  applications: Application[]
  sources: { id: string; repo: string; commit: string; license: string; copyright: string }[]
  synced: SyncedSource[]
  frozen: boolean
  hours: number
  kinds: AppKind[]
  categories: string[]
}
export type ApplicationBody = Partial<AppMatches> & {
  name?: string
  kind?: AppKind
  category?: string
  part_of?: string | null
  hidden?: boolean
}

export const APPLICATIONS_URL = '/api/applications'

export const saveApplication = (id: string | null, body: ApplicationBody) =>
  id ? put<Application>(`${APPLICATIONS_URL}/${encodeURIComponent(id)}`, body) : post<Application>(APPLICATIONS_URL, body)
export const removeApplication = (id: string) => del<{ ok: boolean }>(`${APPLICATIONS_URL}/${encodeURIComponent(id)}`)
