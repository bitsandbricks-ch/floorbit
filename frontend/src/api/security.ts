// Security findings (floorbit/security.py) and the ports Floorbit shut (floorbit/ports.py).
export type FindingKind = 'rogue-dhcp' | 'arp-spoof' | 'mac-flap' | 'loop' | 'storm' | 'other'
export type Severity = 'high' | 'medium' | 'low'
export interface Finding {
  id: string
  plugin: string
  plugin_name: string
  kind: FindingKind
  severity: Severity
  title: string
  detail: string
  switch: string
  port: string
  seat: string
  mac: string
  ip: string
  evidence: string[]
  first_seen: number
  last_seen: number
  cleared_at?: number
  /** Why the port is an uplink (a topology link, an LLDP/CDP neighbour, the uplink pattern): no Shut port then (#886). */
  uplink?: 'topology' | 'neighbour' | 'pattern' | null
}
export interface ShutPort {
  switch: string
  port: string
  seat: string | null
  by: string
  at: number
  reason: string
}
export interface SecurityList {
  findings: Finding[]
  cleared: Finding[]
  shut_ports: ShutPort[]
  last_poll: number | null
  interval: number
  plugins: number
  can_act: boolean
  needs_login: boolean
}
