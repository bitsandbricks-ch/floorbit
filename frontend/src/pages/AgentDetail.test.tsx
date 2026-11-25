import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, onTestFinished, vi } from 'vitest'
import type { Agent } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import AgentDetail from './AgentDetail'
import { admin, busyAgent } from './agents/fixtures'

afterEach(() => vi.unstubAllGlobals())

const groups = { groups: [], tags: [{ id: 't1', name: 'Site A' }, { id: 't2', name: 'Hall 2' }] }

function open(agent: Agent, tab = '', extra: Record<string, unknown> = {}) {
  const api = fakeFetch({
    'GET /api/auth/me': admin, 'GET /api/inventory/groups': groups,
    'GET /api/agents': { agents: [agent], connected: true, max: 10, protocol: 2, newest_version: agent.version },
    ...extra,
  })
  vi.stubGlobal('fetch', api.fn)
  renderWithApp(
    <Routes><Route path="/settings/agents/:id" element={<AgentDetail />} /><Route path="/settings/agents" element={<p>list</p>} /></Routes>,
    `/settings/agents/${agent.id}${tab ? `?tab=${tab}` : ''}`,
  )
  return api
}

describe('AgentDetail', () => {
  it('shows what it is, what needs a look and its plugins', async () => {
    const api = open(busyAgent(), '', { 'POST /api/agent-plugins/a1b2c3d4/telemetry/unblock': { ok: true, cleared: 1 } })
    expect(await screen.findByRole('heading', { name: 'Spring LAN, hall 2', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('Online, with errors')).toBeInTheDocument()
    expect(screen.getByText('up 3 hours')).toBeInTheDocument()
    for (const chip of ['Version 0.9.0', 'WebSocket (wss)', '192.0.2.20', 'Hall 2', 'protocol 2']) {
      expect(screen.getAllByText(chip).length).toBeGreaterThan(0)
    }
    const look = screen.getByRole('region', { name: 'Needs a look' })
    expect(within(look).getByText('telemetry is failing: cannot listen on 8186')).toBeInTheDocument()
    expect(within(look).getByText(/netbox is not running: this agent does not have this plugin/)).toBeInTheDocument()
    expect(within(look).getByText(/2 calls failed in the last hour, last .*: port_stats: LibreNMS said no/)).toBeInTheDocument()
    expect(within(look).getByText('3 syslog lines dropped')).toBeInTheDocument()
    expect(within(look).getByText(/Login to sw-a-01 with ssh-ops failed .*\(Authentication failed\)/)).toBeInTheDocument()
    fireEvent.click(within(look).getByRole('button', { name: 'Clear, try again' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.path.includes('/unblock'))?.body).toEqual({ device: 'sw-a-01', credential: 'ssh-ops' }))
    const table = screen.getByRole('table', { name: 'Agent plugins' })
    expect(within(table).getByText('lines 52,000 · backlog 0')).toBeInTheDocument()
    expect(within(table).getByText(/: port in use/)).toBeInTheDocument()
    expect(screen.getByText(/syslog 12,345 received, 0 waiting/)).toBeInTheDocument()
    expect(screen.getByText(/check-in note 1,200 shown, 3,400 not needed/)).toBeInTheDocument()
    expect(screen.getByText('Syslog, NetFlow')).toBeInTheDocument()
  })

  it('lists the agent plugins it does not run, and why (#1001)', async () => {
    const plugin = (id: string, enabled: boolean, agent = true) => ({ id, name: id, enabled, agent: agent ? { actions: [], calls: [], sends: [] } : null })
    open({ ...busyAgent(), plugins_off: ['netflow-relay'] }, 'plugins', { 'GET /api/settings/plugins': { plugins: [
      plugin('lancache', true), plugin('shelly', false), plugin('netflow-relay', true), plugin('loki', true), plugin('dhcp', true, false),
    ] } })
    const table = await screen.findByRole('table', { name: 'Agent plugins' })
    const row = (id: string) => within(table).getByText(id).closest('tr') as HTMLElement
    expect(await within(table).findByText('shelly')).toBeInTheDocument()
    expect(within(row('shelly')).getByText('Off on every agent')).toBeInTheDocument()
    expect(within(row('shelly')).getByRole('link', { name: 'Turn it on' })).toHaveAttribute('href', '/settings/plugins/shelly')
    expect(within(row('netflow-relay')).getByText('Left to another agent')).toBeInTheDocument()
    expect(within(row('loki')).getByText("On, but this agent hasn't reported it yet")).toBeInTheDocument()
    expect(within(row('lancache')).getByText('lines 52,000 · backlog 0')).toBeInTheDocument()   // reported: as before
    expect(within(table).queryByText('dhcp')).not.toBeInTheDocument()                           // no part on the agent
  })

  it('lists the devices it collects, what needs a look first', async () => {
    const problem = { driver: 'snmp', kind: 'refused', address: '192.0.2.22:161', detail: 'connection refused', hint: 'nothing listens' }
    open(busyAgent(), 'devices', {
      'GET /api/agents/a1b2c3d4/devices': { agent: { id: 'a1b2c3d4', name: 'Spring LAN, hall 2' }, connected: true, primary: true, error: null, detail: '', devices: [
        { name: 'sw-a-02', inventory_id: 'd2', kind: 'switch', platform: 'ios', address: '192.0.2.22', drivers: ['snmp'], state: 'silent', pinned: true, seen: null, online: false, problems: [problem] },
        { name: 'sw-a-01', inventory_id: 'd1', kind: 'switch', platform: 'ios', address: '192.0.2.21', drivers: ['snmp', 'traps'], state: 'up', pinned: false, seen: Math.floor(Date.now() / 1000) - 30, online: true, ports: 52, macs: 10, arp: 0, neighbours: 2, problems: [] },
      ] },
    })
    const table = await screen.findByRole('table', { name: 'Devices and their state' })
    // Once: on phones the row is a card with the state inline, no second badge under the name (#1107).
    expect(within(table).getAllByText('Sends nothing')).toHaveLength(1)
    expect(within(table).getByText('Given to this agent')).toBeInTheDocument()
    expect(within(table).getAllByText('Sends').length).toBeGreaterThan(0)
    expect(within(table).getByText('52 ports, 10 MACs, 0 ARP, 2 neighbours')).toBeInTheDocument()
    expect(within(table).getAllByRole('button', { name: 'Test now' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('radio', { name: 'Needs a look (1)' }))
    expect(within(table).queryByText('sw-a-01')).not.toBeInTheDocument()
    expect(within(table).getByText('sw-a-02')).toBeInTheDocument()
  })

  it('says when the agent is away, and still lists what it is given', async () => {
    open({ ...busyAgent(), connected: false }, 'devices', {
      'GET /api/agents/a1b2c3d4/devices': { agent: { id: 'a1b2c3d4', name: 'x' }, connected: false, primary: null, error: 'offline', detail: '', devices: [
        { name: 'sw-a-01', inventory_id: 'd1', kind: 'switch', platform: 'ios', address: '192.0.2.21', drivers: ['snmp'], state: 'unknown', pinned: false, seen: null, online: false, problems: [] },
      ] },
    })
    expect(await screen.findByText('The agent is not connected')).toBeInTheDocument()
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Test now' })).not.toBeInTheDocument()
  })

  it('draws its numbers over time and changes the range', async () => {
    // jsdom lays nothing out: give the stat widgets a box, or they draw nothing.
    const w = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(320)
    const h = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(64)
    onTestFinished(() => { w.mockRestore(); h.mockRestore() })
    const now = Math.floor(Date.now() / 1000)
    const pts = (v: number) => [[now - 180, v], [now - 120, v], [now - 60, v + 2]]
    const api = open(busyAgent(), 'graphs', {
      'GET /api/agents/a1b2c3d4/history?hours=6': { hours: 6, series: { points: pts(1200), heard: pts(4), sent: [], median_ms: [] } },
      'GET /api/agents/a1b2c3d4/history?hours=24': { hours: 24, series: {} },
    })
    expect(await screen.findByRole('img', { name: 'Telemetry points' })).toBeInTheDocument()
    // The latest value is the shared stat widget, with its unit (#1321).
    expect(screen.getByText('1,202')).toBeInTheDocument()
    expect(screen.getAllByText('/min').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Per minute').length).toBeGreaterThan(0)
    expect(screen.queryByText('Sends to Floorbit')).not.toBeInTheDocument()       // never sent: left out
    // Lowest, average and highest under each chart, and the value at a point on hover or arrow key (issue #868).
    expect(screen.getByText('min 1,200 · avg 1,201 · max 1,202')).toBeInTheDocument()
    const chart = screen.getByRole('group', { name: 'Telemetry points' })
    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    expect(within(chart).getByRole('status')).toHaveTextContent(/· 1,202$/)
    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    expect(within(chart).getByRole('status')).toHaveTextContent(/· 1,200$/)
    // One chart large.
    fireEvent.click(screen.getByRole('button', { name: 'Show Telemetry points larger' }))
    expect(await screen.findByRole('dialog', { name: 'Telemetry points' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.click(screen.getByText('24 h'))
    expect(await screen.findByText(/No numbers kept yet/)).toBeInTheDocument()
    expect(api.calls.some((c) => c.path.endsWith('hours=24'))).toBe(true)
  })

  it('shows its plugin updates', async () => {
    const now = Date.now() / 1000
    const a: Agent = { ...busyAgent(), report: { at: now, plugins: {},
      updates: { policy: 'approve', image: '0.4.0', signed: true,
        plugins: { lancache: { version: '0.5.0', source: 'bundle', probation: true, rolled_back: [], pending: null },
                   netbox: { version: '0.4.0', source: 'image', probation: false, rolled_back: [], pending: { version: '0.5.0', why: 'waits for approval on the agent' } } },
        events: [{ at: now - 60, plugin: 'lancache', event: 'installed', version: '0.5.0', detail: 'was 0.4.0' },
                 { at: now - 30, plugin: 'telemetry', event: 'rolled back', version: '0.5.0', detail: 'cannot start' }] } } }
    open(a, 'updates')
    expect(await screen.findByText(/Plugin updates wait for approval on the agent · image 0\.4\.0/)).toBeInTheDocument()
    expect(screen.getByText('lancache runs 0.5.0 (update) · being watched')).toBeInTheDocument()
    expect(screen.getByText('netbox 0.5.0 offered: waits for approval on the agent')).toBeInTheDocument()
    expect(screen.getByText('rolled back')).toBeInTheDocument()
    expect(screen.getByText(/telemetry 0\.5\.0 · .* · cannot start/)).toBeInTheDocument()
  })

  it('shows where its own update stands and what the crew does about it', async () => {
    const now = Date.now() / 1000
    const a: Agent = { ...busyAgent(), self_update: { latest: '1.0.0', state: 'approve', why: 'waits for approval on the agent' },
      report: { at: now, plugins: {}, agent_update: { policy: 'approve', running: '0.9.0', image: '0.9.0', trial: false,
        rolled_back: [], events: [{ at: now - 120, event: 'rolled back', version: '0.9.5', detail: 'did not reach Floorbit' }] } } }
    open(a, 'updates')
    const panel = await screen.findByLabelText('Agent update')
    expect(within(panel).getByText('Approve on the agent')).toBeInTheDocument()
    expect(within(panel).getByText('Runs 0.9.0 · newest release 1.0.0')).toBeInTheDocument()
    expect(within(panel).getByText('docker compose exec agent python -m floorbit_agent_boot update approve')).toBeInTheDocument()
    expect(within(panel).getByText(/0\.9\.5 · .* · did not reach Floorbit/)).toBeInTheDocument()
    expect(screen.getByText("This agent hasn't said anything about plugin updates yet (older agents don't).")).toBeInTheDocument()
  })

  it('tells the crew to pull the new image for an agent that can\'t update itself', async () => {
    open({ ...busyAgent(), self_update: { latest: '1.0.0', state: 'pull', why: '' } }, 'updates')
    expect(await screen.findByText('Pull the new image')).toBeInTheDocument()
    expect(screen.getByText('docker compose pull && docker compose up -d')).toBeInTheDocument()
  })

  it('changes its settings: a new key, a new name, its tags, revoke', async () => {
    const a = { ...busyAgent(), plugins_off: ['shelly'] }
    const api = open(a, 'settings', {
      [`POST /api/agents/${a.id}/rotate`]: { id: a.id, name: a.name, key: 'fba_a1b2c3d4_another-example-key-012345' },
      [`PATCH /api/agents/${a.id}`]: { id: a.id },
      [`DELETE /api/agents/${a.id}`]: { ok: true },
    })
    expect(await screen.findByText('Plugins it leaves off')).toBeInTheDocument()
    expect(await screen.findByText('Answers for')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'New key' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    expect(await screen.findByText('fba_a1b2c3d4_another-example-key-012345')).toBeInTheDocument()
    expect(screen.getByText(`New key for ${a.name}`)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }))
    fireEvent.change(screen.getByLabelText('New name'), { target: { value: 'Hall 2 agent' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'Hall 2 agent' }))
    await vi.waitFor(() => expect(screen.queryByLabelText('New name')).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Revoke' })).getByRole('button', { name: 'Yes, go ahead' }))
    expect(await screen.findByText('list')).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'DELETE')).toBe(true)
  })

  it('says when the agent is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/inventory/groups': groups, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Routes><Route path="/settings/agents/:id" element={<AgentDetail />} /></Routes>, '/settings/agents/nope')
    expect(await screen.findByText('No such agent')).toBeInTheDocument()
  })
})
