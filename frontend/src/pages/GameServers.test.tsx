import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GameServer, GameServerList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import GameServers from './GameServers'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'te', display_name: 'Te', role: 'tech', permissions: ['floorplan.view', 'games.rcon'] } }
const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['floorplan.view', 'games.rcon', 'settings.manage'] } }
const cs: GameServer = {
  id: 'g1', name: 'CS Hall A', game: 'Counter-Strike 2', host: '192.0.2.50', port: 27015, query: 'a2s', rcon_port: 27015, rcon: true,
  status: 'up', error: '', checked_at: 1_763_100_000, since: 1_763_090_000,
  info: { name: 'Hall A 5on5', map: 'de_example', game: 'Counter-Strike', version: '1.40', players: 7, max_players: 10, bots: 0, ping_ms: 2.1 },
  history: [[1_763_099_940, 5], [1_763_099_970, 6], [1_763_100_000, 7]],
}
const mc: GameServer = { ...cs, id: 'g2', name: 'Minecraft', game: 'Minecraft', query: 'minecraft', rcon: false, rcon_port: null,
  status: 'down', info: null, error: 'No answer to the server query.', history: [] }
const list: GameServerList = { servers: [cs, mc], interval: 30, last_poll: 1_763_100_000, via_agent: false,
  counts: { up: 1, down: 1, unknown: 0 }, players: 7 }

describe('GameServers', () => {
  it('shows each server and sends RCON, asking before a command that changes the map', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/game-servers': list,
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
    renderWithApp(<GameServers />)
    const card = await screen.findByRole('region', { name: 'CS Hall A' })
    expect(within(card).getByText('7/10')).toBeInTheDocument()
    expect(within(card).getByText('Map de_example · 2.1 ms · 1.40')).toBeInTheDocument()
    expect(screen.getByText('1 of 2 servers up · 7 players')).toBeInTheDocument()
    const down = screen.getByRole('region', { name: 'Minecraft' })
    expect(within(down).getByText('No answer to the server query.')).toBeInTheDocument()
    expect(within(down).getByRole('button', { name: 'RCON console' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Add game server' })).not.toBeInTheDocument()   // admins only

    fireEvent.click(within(card).getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/game-servers/check/g1')).toBe(true))
    fireEvent.click(within(card).getByRole('button', { name: 'RCON console' }))
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

  it('lets admins add a server with a write-only RCON password', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/game-servers': { ...list, servers: [], counts: { up: 0, down: 0, unknown: 0 }, players: 0 },
      'POST /api/game-servers': () => ({ status: 201, body: cs }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<GameServers />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add game server' }))
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
