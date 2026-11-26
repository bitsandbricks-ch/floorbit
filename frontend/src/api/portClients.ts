import type { SharedPort } from './walkThrough'

/** Clients on seat ports the patch plan doesn't explain (issue #473), from MAC tables and ARP. */
/** The rough area a port goes to (floorbit/port_areas.py). */
export interface PortAreaHint { label: string; seats: string[] }
export interface PortArea { id: string; switch: string; first: number; last: number; seats: string[]; label: string; updated_at?: number; by?: string | null }
export interface PortClient { switch: string; port: string; mac: string; ip: string; ip_seat: string; seat?: string; cable?: string; area?: PortAreaHint | null }
export interface PortClients {
  as_of: number | null; reading: boolean; started: boolean; error: string | null; switches: number; clients: number
  failed: { switch: string; error: string }[]
  unplanned: { count: number; rows: PortClient[] }; moved: { count: number; rows: PortClient[] }
  /** Seat ports with more than one machine (issue #1119): only how many, never which. */
  shared?: { count: number; rows: SharedPort[] }
  /** Issue #949: IPs ARP knows on no seat port, and cabled seats with no machine (once check-ins started). */
  no_port?: { count: number; rows: { mac: string; ip: string; ip_seat: string }[] }
  empty?: { count: number; rows: { seat: string; switch: string; port: string }[] }
  ignored?: number
}
