import type { DeviceSeen, DeviceState, DeviceStateRow } from './api'

type GivenDevice = { name: string; inventory_id: string; kind: string; platform: string; address: string; drivers: string[] }

/** A device's state from what the collector last said, the same rule as the agent's Devices tab
 *  (floorbit/agent_devices.py ``_state``), so both pages read alike. */
export function stateOf(seen: DeviceSeen | undefined, drivers: string[]): DeviceState {
  if (!seen) return 'unknown'
  const problems = (seen.problems ?? []).length > 0
  if (seen.online) return problems ? 'partial' : 'up'
  if (problems) return 'silent'
  // Traps come when something happens: a quiet trap-only device is not a problem.
  if (drivers.length && drivers.every((d) => d === 'traps' || d === 'mdt')) return 'waiting'
  return seen.seen ? 'silent' : 'never'
}

export const NEEDS_LOOK: DeviceState[] = ['silent', 'never', 'partial']

/** Every device with its state, what needs a look first. A device that sends by itself without
 *  being in the inventory is listed too, as "sends by itself". */
export function deviceRows(d: { devices: GivenDevice[]; seen: Record<string, DeviceSeen> }): DeviceStateRow[] {
  const known = new Set(d.devices.map((x) => x.name.toLowerCase()))
  const rows: DeviceStateRow[] = d.devices.map((x) => {
    const s = d.seen[x.name] ?? { seen: null, online: false }
    return { ...s, name: x.name, inventory_id: x.inventory_id, kind: x.kind, platform: x.platform, address: x.address,
      drivers: x.drivers, pinned: false, state: stateOf(s, x.drivers) }
  })
  for (const [name, s] of Object.entries(d.seen)) {
    if (!known.has(name.toLowerCase()) && s.seen) {
      rows.push({ ...s, name, inventory_id: null, kind: '', platform: '', address: '', drivers: [], pinned: false, pushed: true,
        state: stateOf(s, []) })
    }
  }
  return rows.sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.name.localeCompare(b.name))
}

/** "Needs a look" first: the default sort of every device list. */
export const ORDER: Record<DeviceState, number> = { silent: 0, never: 1, partial: 2, unknown: 3, waiting: 4, standby: 5, up: 6 }

