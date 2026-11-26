import type { Device } from '@/api/types'

export const TIERS = ['core', 'distribution', 'access'] as const
export type Tier = (typeof TIERS)[number] | ''
export type SwitchState = 'up' | 'errors' | 'down' | 'unknown'

export interface SwitchRow { d: Device; tier: Tier; state: SwitchState }

/** The inventory's switches as the Switches tab lists them (issue #902). The tier comes from the
 *  topology, not from a field someone has to fill in: a switch others uplink to and that has no
 *  uplink itself is core, one with seats or nobody below it is access, the rest distribution. */
export function switchRows(devices: Device[]): SwitchRow[] {
  const switches = devices.filter((d) => d.role === 'switch')
  const below = new Set(switches.flatMap((d) => (d.uplink ? [d.uplink.peer.toLowerCase()] : [])))
  const anyUplink = switches.some((d) => d.uplink)
  return switches.map((d) => {
    const feeds = below.has(d.name.toLowerCase())
    const tier: Tier = !anyUplink ? ''
      : !d.uplink && feeds ? 'core'
        : (d.seats ?? 0) > 0 || !feeds ? (d.uplink ? 'access' : '')
          : 'distribution'
    return { d, tier, state: stateOf(d) }
  })
}

function stateOf(d: Device): SwitchState {
  if (d.state === 'offline') return 'down'
  if (d.state !== 'online') return 'unknown'
  return d.uplink?.issue ? 'errors' : 'up'
}
