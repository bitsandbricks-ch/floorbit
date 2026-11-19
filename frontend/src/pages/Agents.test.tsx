import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Agents from './Agents'
import { admin, busyAgent, quietAgent } from './agents/fixtures'

afterEach(() => vi.unstubAllGlobals())

const halls = { halls: [{ id: 'main', name: 'Main hall' }, { id: 'h2', name: 'Hall 2' }] }

describe('Agents', () => {
  it('shows every agent at a glance and enrols one', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': {
        agents: [busyAgent(), quietAgent({ id: 'b', name: 'Old site', connected: false, last_seen: null, version: null }),
          quietAgent({ id: 'c', name: 'Old box', connected: false, version: '0.0.9', protocol: 1, outdated: true, last_seen: Date.now() / 1000 - 3600 })],
        connected: true, max: 10, server_version: '0.1.0', protocol: 2, newest_version: '0.9.0',
      },
      'GET /api/halls': halls,
      'POST /api/agents': { ...busyAgent(), id: 'e5f6a7b8', name: 'Autumn LAN', connected: false, last_seen: null, key: 'fba_e5f6a7b8_example-key-0123456789' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Agents />)
    const card = (await screen.findByRole('article', { name: 'Spring LAN, hall 2' }))
    // The four figures over all agents
    const tiles = screen.getByLabelText('Overview')
    expect(within(tiles).getAllByText('1 / 3')).toHaveLength(2)    // online, plugins healthy
    expect(within(tiles).getByText('Spring LAN, hall 2, Old site, Old box')).toBeInTheDocument()
    expect(within(tiles).getByText('2 failed')).toBeInTheDocument()
    // One card: status, facts, plugins and what needs a look
    expect(within(card).getByText('Online, with errors')).toBeInTheDocument()
    expect(within(card).getByText('WebSocket (wss)')).toBeInTheDocument()
    expect(within(card).getByText('3 hours')).toBeInTheDocument()
    expect(within(card).getByText('2 reconnects')).toBeInTheDocument()
    expect(within(card).getByText('412 calls · 84 ms')).toBeInTheDocument()
    expect(await within(card).findByText('Hall 2')).toBeInTheDocument()
    expect(within(within(card).getByLabelText('Plugins')).getByText('lancache')).toBeInTheDocument()
    expect(within(card).getByText('telemetry is failing: cannot listen on 8186')).toBeInTheDocument()
    expect(within(card).getByText(/and \d+ more/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Open Spring LAN, hall 2' })).toHaveAttribute('href', '/settings/agents/a1b2c3d4')
    const never = screen.getByRole('article', { name: 'Old site' })
    expect(within(never).getByText('Offline')).toBeInTheDocument()
    expect(within(never).getByText(/Never connected/)).toBeInTheDocument()
    const old = screen.getByRole('article', { name: 'Old box' })
    expect(within(old).getByText('Update')).toBeInTheDocument()
    expect(within(old).getByText(/older agent protocol than this Floorbit \(2\)/)).toBeInTheDocument()
    // Enrol
    fireEvent.click(screen.getByRole('button', { name: 'Enrol an agent' }))
    fireEvent.change(await screen.findByLabelText(/^Name/), { target: { value: 'Autumn LAN' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enrol' }))
    expect(await screen.findByText('fba_e5f6a7b8_example-key-0123456789')).toBeInTheDocument()
    expect(screen.getByText(/FLOORBIT_AGENT_KEY=fba_e5f6a7b8_example-key-0123456789/)).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST' && c.path === '/api/agents')?.body).toEqual({ name: 'Autumn LAN' })
  })

  it('says what to do about a plugin warning, in words and with a link', async () => {
    const agent = busyAgent()
    agent.report!.plugins = {
      telemetry: { status: 'warning', hint: 'telegraf_missing', message: 'nothing from Telegraf', running: true, metrics: {}, errors: [] },
      dns: { status: 'warning', hint: 'device_problems', message: '1 of 2 devices fail', running: true, metrics: {}, errors: [] },
    }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/halls': halls,
      'GET /api/agents': { agents: [agent], connected: true, max: 10, server_version: '0.1.0', protocol: 2, newest_version: '0.9.0' },
    }).fn)
    renderWithApp(<Agents />)
    const card = await screen.findByRole('article', { name: 'Spring LAN, hall 2' })
    expect(within(card).getByText(/telemetry: Nothing from Telegraf: this agent image has no Telegraf/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'How to fix' })).toHaveAttribute('href', expect.stringContaining('docs/agent.md#telegraf'))
    expect(within(card).getByRole('link', { name: 'Show devices' })).toHaveAttribute('href', '/settings/telemetry')
  })

  it('flags an agent behind the newest one', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/halls': halls,
      'GET /api/agents': { agents: [quietAgent({ id: 'x', name: 'Behind', version: '0.9.0', report: { at: Date.now() / 1000 } }), quietAgent({ id: 'y', name: 'Ahead', version: '0.10.0' })],
        connected: true, max: 10, protocol: 2, newest_version: '0.10.0' },
    }).fn)
    renderWithApp(<Agents />)
    const card = await screen.findByRole('article', { name: 'Behind' })
    expect(within(card).getByText(/Runs 0\.9\.0, another agent runs 0\.10\.0/)).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'Ahead' })).queryByText('Update')).toBeNull()
  })

  it('says the plugins answer while there is no agent', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText(/No agent yet/)).toBeInTheDocument()
  })

  it('shows failover per hall and this Floorbit on their tabs', async () => {
    const now = Date.now() / 1000
    const a = busyAgent()
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/halls': { halls: [] },
      'GET /api/agents': {
        agents: [a], connected: true, max: 10, protocol: 2,
        groups: [{ id: '*', halls: [], label: '', state: 'degraded', mode: 'active-passive', primary: a.id, vips: ['192.0.2.10/24'],
          agents: [{ id: a.id, name: a.name, connected: true, role: 'primary', holds: ['192.0.2.10/24'] },
                   { id: 'b', name: 'Backup box', connected: false, role: 'offline', holds: [] }] }],
        hosted: { mode: 'redis', pods: [{ pod: 'floorbit-0', at: now, leader: true, me: true }, { pod: 'floorbit-1', at: now, leader: false, me: false }],
          database: { kind: 'postgres', ok: true }, redis: { ok: true } },
      },
    }).fn)
    renderWithApp(<Agents />)
    fireEvent.click(await screen.findByRole('tab', { name: /Failover per hall · 1/ }))
    expect(await screen.findByText('Backup missing')).toBeInTheDocument()
    expect(screen.getByText('active/passive')).toBeInTheDocument()
    expect(screen.getByText(/Spring LAN, hall 2 · primary · 192\.0\.2\.10\/24/)).toBeInTheDocument()
    expect(screen.getByText('Backup box · offline')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'This Floorbit' }))
    expect(await screen.findByText('2 instances share the work over Valkey.')).toBeInTheDocument()
    expect(screen.getByText(/floorbit-0 · leader · this page/)).toBeInTheDocument()
    expect(screen.getByText('Database (postgres) answers.')).toBeInTheDocument()
  })
})

describe('AgentsView on a dashboard', () => {
  it('shows the figures and only the agents that need a look', async () => {
    const { default: AgentsView } = await import('./agents/AgentsView')
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/halls': halls,
      'GET /api/agents': { agents: [busyAgent(), quietAgent({ id: 'ok', name: 'Calm one', report: { at: Date.now() / 1000 } })], connected: true, max: 10, protocol: 2, newest_version: '0.9.0' },
    }).fn)
    renderWithApp(<AgentsView expanded={false} />)
    const look = await screen.findByLabelText('Needs a look')
    expect(within(look).getByRole('link', { name: 'Spring LAN, hall 2' })).toHaveAttribute('href', '/settings/agents/a1b2c3d4')
    expect(within(look).queryByText('Calm one')).toBeNull()
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(screen.queryByRole('article')).toBeNull()
  })
})
