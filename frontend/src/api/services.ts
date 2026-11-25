import type { OwnCheck } from './serviceChecks'

/** GET /api/services (issue #471): ISP uplinks, DNS resolvers, internet sites and the LAN cache. */
export type ServiceStatus = 'up' | 'warn' | 'down' | 'unknown'
interface ServiceState { status: ServiceStatus; since: number | null; checked_at: number | null; history: [number, number | null][]; error: string }
export interface IspUplink extends ServiceState {
  id: string; name: string; device: string; port: string; capacity_mbps: number; probe_host: string; probe_port: number
  port_state?: string | null; in_bps?: number | null; out_bps?: number | null; utilization?: number | null
  latency_ms?: number | null; loss?: number | null
}
export interface DnsResolver extends ServiceState {
  id: string; name: string; address: string; lookup: string; latency_ms?: number | null; rcode?: string | null; answers?: number | null
}
export interface InternetSite extends ServiceState {
  id: string; name: string; host: string; port: number; latency_ms?: number | null; loss?: number | null
}
export interface LanCacheState {
  status: ServiceStatus; hit_ratio: number | null; served_bytes: number; bps: number
  disk: { used: number; total: number; ratio: number } | null; error: string; demo: boolean
}
export interface Services {
  uplinks: IspUplink[]; resolvers: DnsResolver[]; sites: InternetSite[]; checks?: OwnCheck[]; lan_cache: LanCacheState | null
  interval: number; last_poll: number | null; via_agent: boolean; probe_ports: number[]; devices: string[]
}
