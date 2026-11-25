/** One pfSense or OPNsense packet filter line (program "filterlog"), read from its comma list. */
export interface Filterlog {
  action: string
  direction: string
  iface: string
  proto: string
  src: string
  dst: string
  srcPort: string
  dstPort: string
}

const PORTS = new Set(['tcp', 'udp', 'sctp'])

/** The fields that matter of a filterlog line (issue #1429), or null when it isn't one. The layout
 *  is pfSense's and OPNsense's: rule, sub rule, anchor, tracker, interface, reason, action,
 *  direction, IP version, then the IPv4 or IPv6 header fields, then ports for TCP and UDP. */
export function parseFilterlog(message: string): Filterlog | null {
  const f = message.trim().split(',')
  if (f.length < 9) return null
  const [iface, , action, direction, version] = f.slice(4, 9)
  if (!action || !direction) return null
  // The header fields before the protocol differ: IPv4 has six, IPv6 three, and the name and
  // number swap places.
  const at = version === '4' ? { proto: 16, src: 18 } : version === '6' ? { proto: 12, src: 15 } : null
  if (!at || f.length < at.src + 2) return null
  const proto = f[at.proto].toLowerCase()
  const ports = PORTS.has(proto)
  return {
    action, direction, iface, proto,
    src: f[at.src], dst: f[at.src + 1],
    srcPort: ports ? f[at.src + 2] ?? '' : '', dstPort: ports ? f[at.src + 3] ?? '' : '',
  }
}

const hostPort = (host: string, port: string) => (!port ? host : host.includes(':') ? `[${host}]:${port}` : `${host}:${port}`)

/** "block in · igb1 · UDP 203.0.113.9:123 → 198.51.100.1:123" */
export function filterlogText(p: Filterlog): string {
  return `${p.action} ${p.direction} · ${p.iface} · ${p.proto.toUpperCase()} ${hostPort(p.src, p.srcPort)} → ${hostPort(p.dst, p.dstPort)}`
}
