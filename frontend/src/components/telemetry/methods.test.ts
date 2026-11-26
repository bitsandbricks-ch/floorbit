import { describe, expect, it } from 'vitest'
import type { DeviceStateRow } from './api'
import { methodCells } from './methods'

const row = (over: Partial<DeviceStateRow>): DeviceStateRow => ({
  name: 'sw-a-01', inventory_id: 'd1', kind: 'switch', platform: 'ios', address: '192.0.2.10', drivers: ['snmp', 'traps'],
  state: 'up', pinned: false, seen: 1_763_100_000, online: true, ...over,
})
const states = (r: DeviceStateRow, syslog?: number) => Object.fromEntries(methodCells(r, syslog).map((c) => [c.method, c.state]))

describe('methodCells (#904)', () => {
  it('marks what is set up and heard, and what is not set up', () => {
    expect(states(row({}), 1_763_100_000)).toEqual({ snmp: 'ok', traps: 'ok', syslog: 'ok', api: 'off', gnmi: 'off', mdt: 'off' })
  })
  it('puts an error on the method it belongs to', () => {
    const r = row({ problems: [{ driver: 'snmp', kind: 'timeout', address: '192.0.2.10:161', detail: '' }] })
    expect(states(r).snmp).toBe('err')
    expect(states(r).traps).toBe('ok')
  })
  it('tells a quiet device from one never heard; traps only come with events', () => {
    expect(states(row({ online: false }))).toMatchObject({ snmp: 'late', traps: 'ok' })
    expect(states(row({ online: false, seen: null }))).toMatchObject({ snmp: 'never', traps: 'ok' })
  })
})
