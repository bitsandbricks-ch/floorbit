import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Agents from './Agents'
import { admin, busyAgent, quietAgent } from './agents/fixtures'

afterEach(() => vi.unstubAllGlobals())

/** The agents' rows, without the groups' header rows. */
const dataRows = () => screen.getAllByRole('row').filter((r) => r.closest('tbody') && !r.classList.contains('bnb-dt-group-head'))

/** The agents under a group's header row, in order. */
const agentRows = (name: string) => {
  const head = screen.getAllByRole('heading').find((h) => h.textContent?.includes(name))
  const body = head?.closest('tbody')
  return body ? within(body).getAllByRole('row').filter((r) => !r.classList.contains('bnb-dt-group-head')) : []
}

const groups = { groups: [], tags: [{ id: 't1', name: 'Site A' }, { id: 't2', name: 'Hall 2' }] }

describe('Agents', () => {
  it('lists every agent grouped, problems first, and enrols one', async () => {
    const now = Date.now() / 1000
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': {
        agents: [quietAgent({ id: 'q', name: 'Calm hall', report: { at: now } }), busyAgent(),
          quietAgent({ id: 'b', name: 'Old site', connected: false, last_seen: null, version: null, tags: ['t1'] }),
          quietAgent({ id: 'c', name: 'Old box', connected: false, version: '0.0.9', protocol: 1, outdated: true, last_seen: now - 3600, tags: ['t1'] })],
        connected: true, max: 10, server_version: '0.1.0', protocol: 2, newest_version: '0.9.0',
        groups: [
          { id: 't1', tags: ['t1'], label: 'Site A', state: 'down', mode: null, primary: null, vips: [],
            agents: [{ id: 'b', name: 'Old site', connected: false, role: 'offline', holds: [] }, { id: 'c', name: 'Old box', connected: false, role: 'offline', holds: [] }] },
          { id: 't2', tags: ['t2'], label: 'Hall 2', state: 'ok', mode: 'active-active', primary: 'a1b2c3d4', vips: [],
            agents: [{ id: 'a1b2c3d4', name: 'Spring LAN, hall 2', connected: true, role: 'primary', holds: [] }, { id: 'q', name: 'Calm hall', connected: true, role: 'active', holds: [] }] },
        ],
      },
      'GET /api/agents/load': { hours: 1, agents: { a1b2c3d4: { load: [[0, 100], [60, 160]], syslog: 120 } } },
      'GET /api/inventory/groups': groups,
      'POST /api/agents': { ...busyAgent(), id: 'e5f6a7b8', name: 'Autumn LAN', connected: false, last_seen: null, key: 'fba_e5f6a7b8_example-key-0123456789' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Agents />)
    const list = await screen.findByLabelText('Agents by group')
    // The four figures
    expect(screen.getByText('2 / 4')).toBeInTheDocument()                     // online
    expect(screen.getByText('Old box, Old site, Spring LAN, hall 2')).toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()                     // failover ready: Hall 2, not Site A
    expect(screen.getByText('1 runs an older version, newest 0.9.0')).toBeInTheDocument()
    // Groups with problems first, and the agents in them too
    const heads = within(list).getAllByRole('heading')
    expect(heads.map((h) => h.textContent)).toEqual([expect.stringContaining('Site A'), expect.stringContaining('Hall 2')])
    expect(within(heads[1]).getByText('Failover ready')).toBeInTheDocument()
    const hall = agentRows('Hall 2')
    expect(hall.map((r) => r.textContent)).toEqual([expect.stringContaining('Spring LAN, hall 2'), expect.stringContaining('Calm hall')])
    const busy = hall[0]
    expect(within(busy).getByText('Primary')).toBeInTheDocument()
    expect(within(busy).getByText('192.0.2.20')).toBeInTheDocument()
    expect(await within(busy).findByRole('img', { name: '160 telemetry points and syslog lines per minute now' })).toBeInTheDocument()
    expect(within(busy).getByText('2')).toBeInTheDocument()                     // syslog lines/s: 120 a minute
    expect(within(busy).getByText(/netbox/)).toBeInTheDocument()                // the worst problem, then how many more
    expect(within(busy).getByText(/and \d+ more/)).toBeInTheDocument()
    expect(within(agentRows('Site A').find((r) => r.textContent?.includes('Old box'))!).getByText('Update')).toBeInTheDocument()
    // A row opens the agent beside the list
    fireEvent.click(within(busy).getByText('Spring LAN, hall 2'))
    const panel = await screen.findByRole('dialog')
    expect(within(panel).getByText('WebSocket (wss)')).toBeInTheDocument()
    expect(within(panel).getByText('412 calls · 84 ms')).toBeInTheDocument()
    expect(within(within(panel).getByLabelText('Plugins')).getByText('lancache')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Clear, try again' })).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /Open agent page/ })).toHaveAttribute('href', '/settings/agents/a1b2c3d4')
    fireEvent.click(within(panel).getByRole('button', { name: /close/i }))
    // Filters: only the older ones, from the head's update button
    fireEvent.click(screen.getByRole('button', { name: 'Update 1 agent' }))
    await vi.waitFor(() => expect(agentRows('Site A').map((r) => r.textContent)).toEqual([expect.stringContaining('Old box')]))
    expect(within(list).queryByRole('heading', { name: /Hall 2/ })).toBeNull()
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
      'GET /api/auth/me': admin, 'GET /api/inventory/groups': groups,
      'GET /api/agents': { agents: [agent], connected: true, max: 10, server_version: '0.1.0', protocol: 2, newest_version: '0.9.0' },
    }).fn)
    renderWithApp(<Agents />)
    await screen.findByRole('table')
    fireEvent.click(within(dataRows()[0]).getByText('Spring LAN, hall 2'))
    const panel = await screen.findByRole('dialog')
    expect(within(panel).getByText(/telemetry: Nothing from Telegraf: this agent image has no Telegraf/)).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'How to fix' })).toHaveAttribute('href', expect.stringContaining('docs/agent.md#telegraf'))
    // Device problems open this agent's own Devices tab, on what needs a look.
    expect(within(panel).getAllByRole('link', { name: 'Show devices' })[0]).toHaveAttribute('href', '/settings/agents/a1b2c3d4?tab=devices&show=look')
  })

  it('flags an agent behind the newest one', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/inventory/groups': groups,
      'GET /api/agents': { agents: [quietAgent({ id: 'x', name: 'Behind', version: '0.9.0', report: { at: Date.now() / 1000 } }), quietAgent({ id: 'y', name: 'Ahead', version: '0.10.0' })],
        connected: true, max: 10, protocol: 2, newest_version: '0.10.0' },
    }).fn)
    renderWithApp(<Agents />)
    await screen.findByRole('table')
    const row = dataRows().find((r) => r.textContent?.includes('Behind'))!
    expect(within(row).getByText(/Runs 0\.9\.0, another agent runs 0\.10\.0/)).toBeInTheDocument()
    expect(within(row).getByText('Update')).toBeInTheDocument()
    expect(within(dataRows().find((r) => r.textContent?.includes('Ahead'))!).queryByText('Update')).toBeNull()
  })

  it('says the plugins answer while there is no agent', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText(/No agent yet/)).toBeInTheDocument()
  })

  it('shows how a group fails over, and this Floorbit', async () => {
    const now = Date.now() / 1000
    const a = busyAgent()
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/inventory/groups': { groups: [], tags: [] },
      'GET /api/agents': {
        agents: [a, quietAgent({ id: 'b', name: 'Backup box', connected: false, last_seen: now - 60 })], connected: true, max: 10, protocol: 2,
        groups: [{ id: '*', tags: [], label: '', state: 'degraded', mode: 'active-passive', primary: a.id, vips: ['192.0.2.10/24'],
          agents: [{ id: a.id, name: a.name, connected: true, role: 'primary', holds: ['192.0.2.10/24'] },
                   { id: 'b', name: 'Backup box', connected: false, role: 'offline', holds: [] }] }],
        hosted: { mode: 'redis', pods: [{ pod: 'floorbit-0', at: now, leader: true, me: true }, { pod: 'floorbit-1', at: now, leader: false, me: false }],
          database: { kind: 'postgres', ok: true }, redis: { ok: true } },
      },
    }).fn)
    renderWithApp(<Agents />)
    const head = (await screen.findAllByRole('heading', { name: /Every device/ }))[0]
    expect(within(head).getByText('Backup missing')).toBeInTheDocument()
    expect(within(head).getByText('2 agents')).toBeInTheDocument()
    // The shared addresses, active/passive, what's wrong, and which agent holds which address
    expect(within(head).getByText('active/passive')).toBeInTheDocument()
    expect(within(head).getByText('192.0.2.10/24')).toBeInTheDocument()
    expect(screen.getByText(/a backup agent is offline/)).toBeInTheDocument()
    const primary = dataRows().find((r) => r.textContent?.includes('Spring LAN, hall 2'))!
    expect(within(primary).getByText('192.0.2.10/24')).toBeInTheDocument()
    expect(screen.getByText('0 / 1')).toBeInTheDocument()                        // failover ready
    expect(screen.getByText('2 instances share the work over Valkey.')).toBeInTheDocument()
    expect(screen.getByText(/floorbit-0 · leader · this page/)).toBeInTheDocument()
    expect(screen.getByText('Database (postgres) answers.')).toBeInTheDocument()
  })
})

describe('AgentsView on a dashboard', () => {
  it('shows the figures and only the agents that need a look', async () => {
    const { default: AgentsView } = await import('./agents/AgentsView')
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/inventory/groups': groups,
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
