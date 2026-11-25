/** Own checks on the Services page (issue #1338) and service tags (#1337): floorbit/services.py. */

export type CheckKind = 'ping' | 'tcp' | 'udp' | 'http'
export type UdpAsk = 'dns' | 'ntp' | 'a2s' | 'none'
export const CHECK_KINDS: CheckKind[] = ['ping', 'tcp', 'udp', 'http']
export const UDP_ASKS: UdpAsk[] = ['dns', 'ntp', 'a2s', 'none']

/** What the crew sets up. */
export interface OwnCheckFields {
  name: string; kind: CheckKind; host: string; port: number | null; ask: UdpAsk | ''; url: string
  expect: string; contains: string; cert_warn_days: number | null; slow_ms: number
  /** "Checked from" (issue #1444): '' any agent, ``tag:<id>`` the agents with a tag, or an agent id. */
  from?: string
}

/** What the last run saw, next to it. */
export interface OwnCheckResult {
  status: 'up' | 'warn' | 'down' | 'unknown'
  latency_ms: number | null; loss: number | null; code: number | null; cert_days: number | null
  error: string; note?: string
}

export interface OwnCheck extends OwnCheckFields, OwnCheckResult {
  id: string; since: number | null; checked_at: number | null; history: [number, number | null][]
}

/** {service id from the summary: tags}. */
export type ServiceTags = Record<string, string[]>
