import type { AgentPluginHealth } from './agents'

export interface CacheRow { cache: string; hit_bytes: number; miss_bytes: number; requests: number }
export interface LancacheData {
  configured: boolean
  demo: boolean
  hours: { t: number; hit_bytes: number; miss_bytes: number }[]
  hit_bytes: number
  miss_bytes: number
  hit_ratio: number | null
  caches: CacheRow[]
  last_read: number | null
  error: string | null
}
/** One agent's view of the LAN cache machine (the lancache agent plugin's status). */
export interface LancacheAgent {
  id: string
  name: string | null
  updated: number | null
  stale: boolean
  disk: { used?: number; total?: number; free?: number; error?: string } | null
  heartbeat: { ok: boolean; ms?: number; processed_by?: string; error?: string } | null
  dns_check: { ok: boolean; error?: string } | null
  clearing: { running: boolean; started: number; finished?: number; removed: number; errors: number } | null
  health: AgentPluginHealth | null
}
export interface LancacheDownload extends CacheRow { item: string; clients: number; hit_ratio: number | null }
export interface LancacheOverview extends LancacheData {
  plugin_on: boolean
  /** False when the plugin is not installed from the Marketplace. */
  plugin_installed?: boolean
  agents: LancacheAgent[]
  downloads: LancacheDownload[]
  other_downloads: { hit_bytes: number; miss_bytes: number; requests: number; items: number }
  suspects: { cache: string; item: string; files: number; misses: number }[]
  dns_services: { cache: string; lookups: number }[]
  clients: { t: number; clients: number }[]
  min_clients: number
  window_hours: number
  saved_bytes: number
}
