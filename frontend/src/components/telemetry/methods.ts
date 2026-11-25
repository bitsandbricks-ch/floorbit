import type { DeviceProblem, DeviceStateRow } from './api'

/** The grid's columns on Agents › Telemetry collector (issue #904): one per way a device reports. */
export const METHODS = ['snmp', 'traps', 'syslog', 'api', 'gnmi', 'mdt'] as const
export type Method = (typeof METHODS)[number]

/** ok: heard; late: heard before, quiet now; err: the collector logs an error; never: set up but
 *  nothing came yet; off: not set up for this device. */
export type MethodState = 'ok' | 'late' | 'err' | 'never' | 'off'

export interface MethodCell { method: Method; state: MethodState; at: number | null; problem?: DeviceProblem }

// Which collection types (targets.DRIVERS) each column stands for.
const DRIVERS: Record<Method, string[]> = {
  snmp: ['snmp'], traps: ['traps'], syslog: [], api: ['nxapi', 'restconf', 'opnsense'], gnmi: ['gnmi'], mdt: ['mdt'],
}
// Traps and MDT only come when something happens or on the device's own schedule: quiet is fine.
const EVENTS: Method[] = ['traps', 'mdt']

/** One device's squares, from what the collector last said and when its last syslog line came. */
export function methodCells(r: DeviceStateRow, syslogAt: number | null | undefined): MethodCell[] {
  return METHODS.map((method) => {
    if (method === 'syslog') return { method, state: syslogAt ? 'ok' : 'off', at: syslogAt ?? null }
    const on = r.drivers.some((d) => DRIVERS[method].includes(d))
    if (!on) return { method, state: 'off', at: null }
    const problem = (r.problems ?? []).find((p) => DRIVERS[method].includes(p.driver) || p.driver === method)
    if (problem) return { method, state: 'err', at: r.seen, problem }
    if (r.online) return { method, state: 'ok', at: r.seen }
    if (!r.seen) return { method, state: EVENTS.includes(method) ? 'ok' : 'never', at: null }
    return { method, state: EVENTS.includes(method) ? 'ok' : 'late', at: r.seen }
  })
}

/** The row's worst square: what "with problems" filters on. */
export const rowNeedsLook = (cells: MethodCell[]) => cells.some((c) => c.state === 'err' || c.state === 'late' || c.state === 'never')
