export type IpamSub = 'vlans' | 'prefixes'

/** The IPAM sub-tab an inventory type lives on, or null for types outside IPAM. */
export const ipamSubOf = (type: string): IpamSub | null => (type === 'vlan' ? 'vlans' : type === 'prefix' ? 'prefixes' : null)

export const vlanNum = (v: string | undefined) => (v && /^\d+$/.test(v) ? Number(v) : Number.MAX_SAFE_INTEGER)

/** Sorts addresses as numbers: 192.0.2.0/24 before 192.0.10.0/24; a from-to range by its start. */
export function ipNum(v: string) {
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)/.exec(v.trim())
  if (!m) return Number.MAX_SAFE_INTEGER
  return ((Number(m[1]) * 256 + Number(m[2])) * 256 + Number(m[3])) * 256 + Number(m[4])
}
