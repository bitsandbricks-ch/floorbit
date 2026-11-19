import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GameServer, GameServerList, Services as ServicesData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Services from './Services'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const base = { status: 'up' as const, since: 1, checked_at: 2, error: '', history: [[1, 12], [2, 14]] as [number, number | null][] }
const data: ServicesData = {
  uplinks: [{ ...base, status: 'warn', id: 'u1', name: 'Provider A', device: 'core-01', port: 'Te1/0/48', capacity_mbps: 1000,
    probe_host: 'www.example.com', probe_port: 443, port_state: 'up', in_bps: 850e6, out_bps: 90e6, utilization: 0.85, latency_ms: 12.5, loss: 0.2 }],
  resolvers: [{ ...base, status: 'down', id: 'r1', name: 'Resolver 1', address: '192.0.2.53', lookup: 'example.com', rcode: 'SERVFAIL',
    answers: 0, latency_ms: 3, error: 'example.com: SERVFAIL' }],
  sites: [{ ...base, status: 'down', id: 's1', name: 'Steam', host: 'store.example.com', port: 443, latency_ms: null, loss: null,
    error: 'store.example.com does not answer on port 443.' }],
  lan_cache: { status: 'up', hit_ratio: 0.72, served_bytes: 120e9, bps: 4e8, disk: { used: 8e12, total: 10e12, ratio: 0.8 }, error: '', demo: false },
  interval: 30, last_poll: 2, via_agent: false, probe_ports: [53, 80, 443, 853], devices: ['core-01'],
}

const tech = { enabled: true, user: { username: 'te', display_name: 'Te', role: 'tech', permissions: ['floorplan.view', 'games.rcon'] } }
const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['floorplan.view', 'floorplan.edit', 'games.rcon', 'settings.manage'] } }
const cs: GameServer = {
  id: 'g1', name: 'CS Hall A', game: 'Counter-Strike 2', host: '192.0.2.50', port: 27015, query: 'a2s', rcon_port: 27015, rcon: true,
  status: 'up', error: '', checked_at: 1_763_100_000, since: 1_763_090_000,
  info: { name: 'Hall A 5on5', map: 'de_example', game: 'Counter-Strike', version: '1.40', players: 7, max_players: 10, bots: 0, ping_ms: 2.1 },
  history: [[1_763_099_940, 5], [1_763_099_970, 6], [1_763_100_000, 7]],
}
const mc: GameServer = { ...cs, id: 'g2', name: 'Minecraft', game: 'Minecraft', query: 'minecraft', rcon: false, rcon_port: null,
  status: 'down', info: null, error: 'No answer to the server query.', history: [] }
const games: GameServerList = { servers: [cs, mc], interval: 30, last_poll: 1_763_100_000, via_agent: false,
  counts: { up: 1, down: 1, unknown: 0 }, players: 7 }
const noGames: GameServerList = { ...games, servers: [], counts: { up: 0, down: 0, unknown: 0 }, players: 0 }

describe('Services', () => {
  it('lists every service by type: how full each line is, failing resolvers, the LAN cache and game servers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/services': data, 'GET /api/game-servers': games }).fn)
    renderWithApp(<Services />)
    const line = await screen.findByRole('group', { name: 'Provider A' })
    expect(within(line).getByText('85%')).toBeInTheDocument()
    expect(within(line).getByText('In 850 Mbps · out 90.0 Mbps · 12.5 ms · 20% lost')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Resolver 1' })).getByText('example.com: SERVFAIL')).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'LAN cache' })).getByText('72%')).toBeInTheDocument()
    const game = screen.getByRole('group', { name: 'CS Hall A' })
    expect(within(game).getByText('7/10')).toBeInTheDocument()
    expect(within(game).getByText('Map de_example · 2.1 ms · 1.40')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Game servers' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add service' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'RCON console' })).not.toBeInTheDocument()
  })

  it('filters by state and searches, and groups by state', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/services': data, 'GET /api/game-servers': games }).fn)
    renderWithApp(<Services />)
    await screen.findByRole('group', { name: 'Provider A' })
    fireEvent.click(screen.getByRole('button', { name: 'Show: All' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Not up/ }))
    expect(screen.queryByRole('group', { name: 'CS Hall A' })).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Minecraft' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search services' }), { target: { value: 'steam' } })
    expect(screen.getByRole('group', { name: 'Steam' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Minecraft' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search services' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Group by: Type' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'State' }))
    const down = await screen.findByRole('region', { name: 'Down' })
    expect(within(down).getByRole('group', { name: 'Minecraft' })).toBeInTheDocument()
    expect(within(down).getByText(/^Game server · /)).toBeInTheDocument()
  })

  it('adds a resolver through one Add service button', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/services': { ...data, resolvers: [] }, 'GET /api/game-servers': noGames,
      'POST /api/services/resolvers': () => ({ status: 201, body: data.resolvers[0] }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add service' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'DNS resolver' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'Resolver 1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Address' }), { target: { value: '192.0.2.53' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Name to look up/ }), { target: { value: 'example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      name: 'Resolver 1', address: '192.0.2.53', lookup: 'example.com',
    }))
  })

  it('starts empty with the usual sites in one go', async () => {
    const empty = { ...data, uplinks: [], resolvers: [], sites: [], lan_cache: null }
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/services': empty, 'GET /api/game-servers': noGames,
      'POST /api/services/sites/common': () => ({ status: 200, body: data }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add the usual sites' }))
    const site = await screen.findByRole('group', { name: 'Steam' })
    expect(within(site).getByText('store.example.com does not answer on port 443.')).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/services/sites/common')).toBe(true)
  })

  it('sends RCON to a game server, asking before a command that changes the map', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/services': data, 'GET /api/game-servers': games,
      'POST /api/game-servers/check/g1': () => ({ body: cs }),
      'POST /api/game-servers/rcon/g1': (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body))
        if (body.command.startsWith('changelevel') && !body.confirm) {
          return { status: 409, body: { error: 'Confirm to send it.', confirm: true } }
        }
        return { body: { server: 'CS Hall A', command: body.command, answer: `ran ${body.command}` } }
      },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    const row = await screen.findByRole('group', { name: 'CS Hall A' })
    expect(within(screen.getByRole('group', { name: 'Minecraft' })).getByRole('button', { name: 'RCON console' })).toBeDisabled()
    fireEvent.click(within(row).getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/game-servers/check/g1')).toBe(true))
    fireEvent.click(within(row).getByRole('button', { name: 'RCON console' }))
    const input = await screen.findByRole('textbox', { name: 'Command' })
    fireEvent.change(input, { target: { value: 'status' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('ran status')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'changelevel de_other' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Send this command?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send it' }))
    expect(await screen.findByText('ran changelevel de_other')).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.path === '/api/game-servers/rcon/g1').map((c) => c.body)
    expect(sent).toEqual([{ command: 'status', confirm: false }, { command: 'changelevel de_other', confirm: false },
      { command: 'changelevel de_other', confirm: true }])
  })

  it('lets admins add a game server with a write-only RCON password', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/services': data, 'GET /api/game-servers': noGames,
      'POST /api/game-servers': () => ({ status: 201, body: cs }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add service' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Game server' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'CS Hall A' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Host' }), { target: { value: '192.0.2.50' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'RCON port' }), { target: { value: '27015' } })
    fireEvent.change(screen.getByLabelText('RCON password'), { target: { value: 'example-rcon' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toMatchObject({
      name: 'CS Hall A', host: '192.0.2.50', port: 27015, query: 'a2s', rcon_port: 27015, rcon_password: 'example-rcon',
    }))
  })
})
