// Made-up agents for the Local agents tests (example names and documentation addresses only).
import type { Agent } from '@/api/types'

export const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage', 'plugins.run'] } }

const now = () => Date.now() / 1000

export function busyAgent(): Agent {
  return {
    id: 'a1b2c3d4', name: 'Spring LAN, hall 2', created_at: 1_790_000_000, created_by: 'ada',
    last_seen: now() - 5, version: '0.9.0', address: '192.0.2.20', connected: true, protocol: 2, transport: 'websocket', tags: ['t2'],
    stats: { calls: 412, failed: 2, median_ms: 84, last_error: { at: now() - 60, method: 'port_stats', error: 'LibreNMS said no' } },
    report: { at: now() - 10, up_seconds: 3 * 3600 + 120, reconnects: 2, link_drops: 2, syslog_received: 12345, syslog_backlog: 0, syslog_dropped: 3, flows_packets: 4567, captive_shown: 1200, captive_done: 3400,
      plugins: {
        lancache: { status: 'ok', message: '', running: true, metrics: { lines: 52000, backlog: 0 }, errors: [] },
        telemetry: { status: 'error', message: 'cannot listen on 8186', running: true, metrics: {}, errors: [{ at: now() - 30, error: 'port in use' }],
          auth_blocked: [{ device: 'sw-a-01', credential: 'ssh-ops', rev: '3', since: now() - 120, message: 'Authentication failed' }] },
        netbox: { status: 'error', message: 'this agent does not have this plugin: update the agent', running: false, metrics: {}, errors: [] },
      } },
    relays: { syslog: { at: now() - 3, count: 120 }, flows: { at: now() - 8, count: 6 } },
  }
}

export function quietAgent(over: Partial<Agent>): Agent {
  return { ...busyAgent(), report: null, relays: {}, transport: null, stats: { calls: 0, failed: 0, median_ms: null, last_error: null }, ...over }
}
