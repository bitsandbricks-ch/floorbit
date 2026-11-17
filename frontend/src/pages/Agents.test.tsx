import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Agents from './Agents'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const agent: Agent = {
  id: 'a1b2c3d4', name: 'Spring LAN, hall 2', created_at: 1_790_000_000, created_by: 'ada',
  last_seen: Date.now() / 1000 - 5, version: '0.9.0', address: null, connected: true,
  stats: { calls: 412, failed: 2, median_ms: 84, last_error: { at: Date.now() / 1000 - 60, method: 'port_stats', error: 'LibreNMS said no' } },
  report: { at: Date.now() / 1000 - 10, up_seconds: 3 * 3600 + 120, reconnects: 2, link_drops: 2, syslog_received: 12345, syslog_backlog: 0, syslog_dropped: 3, flows_packets: 4567, captive_shown: 1200, captive_done: 3400,
    plugins: {
      lancache: { status: 'ok', message: '', running: true, metrics: { lines: 52000, backlog: 0 }, errors: [] },
      telemetry: { status: 'error', message: 'cannot listen on 8186', running: true, metrics: {}, errors: [{ at: Date.now() / 1000 - 30, error: 'port in use' }],
        auth_blocked: [{ device: 'sw-a-01', credential: 'ssh-ops', rev: '3', since: Date.now() / 1000 - 120, message: 'Authentication failed' }] },
      netbox: { status: 'error', message: 'this agent does not have this plugin: update the agent', running: false, metrics: {}, errors: [] },
    } },
  relays: { syslog: { at: Date.now() / 1000 - 3, count: 120 }, flows: { at: Date.now() / 1000 - 8, count: 6 } },
}

describe('Agents', () => {
  it('lists agents, enrols one and shows its key and how to start it', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': { agents: [agent, { ...agent, report: null, id: 'b', name: 'Old site', connected: false, last_seen: null, version: null, stats: { calls: 0, failed: 0, median_ms: null, last_error: null } }, { ...agent, report: null, id: 'c', name: 'Old box', connected: false, version: '0.0.9', protocol: 1, outdated: true, stats: undefined }], connected: true, max: 10, server_version: '0.1.0', protocol: 2 },
      'GET /api/halls': { halls: [{ id: 'main', name: 'Main hall' }, { id: 'h2', name: 'Hall 2' }] },
      'PATCH /api/agents/a1b2c3d4': { id: 'a1b2c3d4', halls: ['h2'] },
      'POST /api/agent-plugins/a1b2c3d4/telemetry/unblock': { ok: true, cleared: 1 },
      'POST /api/agents': { ...agent, id: 'e5f6a7b8', name: 'Autumn LAN', connected: false, last_seen: null, key: 'fba_e5f6a7b8_example-key-0123456789' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText('Spring LAN, hall 2')).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.getAllByText('Not connected')).toHaveLength(2)
    expect(screen.getByText(/never connected/)).toBeInTheDocument()
    expect(screen.getByText(/version 0\.9\.0/)).toBeInTheDocument()
    expect(screen.getByText(/412 calls in the last hour, answered in 84 ms/)).toBeInTheDocument()
    expect(screen.getByText('2 failed')).toBeInTheDocument()
    expect(screen.getByText(/port_stats: LibreNMS said no/)).toBeInTheDocument()
    // What the agent reports about itself
    expect(screen.getByText('lancache')).toBeInTheDocument()
    expect(screen.getByText(/running · lines 52,000 · backlog 0/)).toBeInTheDocument()
    expect(screen.getByText(/failing · cannot listen on 8186/)).toBeInTheDocument()
    expect(screen.getByText(/last error .*: port in use/)).toBeInTheDocument()
    expect(screen.getByText(/not running · this agent does not have this plugin/)).toBeInTheDocument()
    expect(screen.getByText(/Login to sw-a-01 with ssh-ops failed .*\(Authentication failed\)\. Not tried again until cleared\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear, try again' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.path.includes('/unblock'))?.body).toEqual({ device: 'sw-a-01', credential: 'ssh-ops' }))
    expect(screen.getByText(/Up 3 hours/)).toBeInTheDocument()
    expect(screen.getByText('2 reconnects')).toBeInTheDocument()
    expect(screen.getByText(/syslog 12,345 received, 0 waiting/)).toBeInTheDocument()
    expect(screen.getByText('3 syslog lines dropped')).toBeInTheDocument()
    expect(screen.getByText(/NetFlow 4,567 packets/)).toBeInTheDocument()
    expect(screen.getByText(/check-in note 1,200 shown, 3,400 not needed/)).toBeInTheDocument()
    expect(screen.getByText('No calls in the last hour')).toBeInTheDocument()
    expect(screen.getByText('Update')).toBeInTheDocument()
    expect(screen.getAllByText('Syslog').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NetFlow').length).toBeGreaterThan(0)
    expect(screen.getByText(/older agent protocol than this Floorbit \(2\)/)).toBeInTheDocument()
    expect(await screen.findAllByText('Answers for')).toHaveLength(3)
    expect(screen.getByText(/With an agent per hall/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Autumn LAN' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enrol' }))
    expect(await screen.findByText('fba_e5f6a7b8_example-key-0123456789')).toBeInTheDocument()
    expect(screen.getByText(/FLOORBIT_AGENT_KEY=fba_e5f6a7b8_example-key-0123456789/)).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST' && c.path === '/api/agents')?.body).toEqual({ name: 'Autumn LAN' })
  })
  it('says the plugins answer while there is no agent', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText(/No agent yet/)).toBeInTheDocument()
  })
})
