/** Links between switches and the topology (issue #468). */
export type LinkType = 'cat5e' | 'cat6' | 'cat6a' | 'fiber-sm' | 'fiber-mm' | 'dac'
export interface SwitchLink {
  id: string; a: string; a_port: string; b: string; b_port: string; type: LinkType | ''; speed: number | null; note: string
  media: 'copper' | 'fiber' | 'dac' | ''
  state: 'up' | 'down' | 'unknown'; speed_bps: number | null; issue: '' | 'down' | 'slow'
  /** What LLDP or CDP sees on its ports (issue #540); null when the source doesn't tell. */
  lldp?: LinkLldp | null
}
export interface LinkLldp { state: 'seen' | 'other' | 'unseen'; at?: 'a' | 'b'; remote?: string; remote_port?: string }
export interface TopologyNode { id: string; name: string; role: string; hall: string; unread: boolean; status: 'online' | 'offline' | 'unknown' }
export interface LinkSuggestion { a: string; a_port: string; b: string; b_port: string; protocol: string; speed: number | null }
/** An internet line from the services view (issue #471), drawn above the box it comes in at. */
export interface TopologyUplink {
  id: string; name: string; device: string; port: string; capacity_mbps: number | null
  status: 'up' | 'warn' | 'down' | 'unknown'; utilization: number | null
}
/** A switch's port for the link form's picker (GET /api/links/ports). */
export interface SwitchPort { name: string; state: string; speed_bps: number | null; used_by: string }
export interface Topology {
  nodes: TopologyNode[]; links: SwitchLink[]; uplinks: TopologyUplink[]; suggestions: LinkSuggestion[]
  counts: { links: number; down: number; slow: number; miswired?: number }; types: LinkType[]; speeds: number[]
  /** Where the crew dragged the boxes, by switch name in lower case; missing or empty: the automatic layout. */
  layout?: Record<string, { x: number; y: number }>
}
