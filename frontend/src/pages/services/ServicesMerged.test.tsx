import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GameServerList, HealthWall, Services as ServicesData, ServiceSummary } from '@/api/types'
import type { OwnCheck } from '@/api/serviceChecks'
import { fakeFetch, renderWithApp } from '@/test/render'
import Services from '../Services'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead',
  permissions: ['floorplan.view', 'floorplan.edit', 'incidents.work'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const encoder: OwnCheck = {
  id: 'c1', name: 'Stream encoder', kind: 'ping', host: '192.0.2.40', port: null, ask: '', url: '', expect: '', contains: '',
  cert_warn_days: null, slow_ms: 100, status: 'up', latency_ms: 1.2, loss: 0, code: null, cert_days: null, error: '',
  since: 1, checked_at: 2, history: [[1, 1.1], [2, 1.2]],
}
const site: OwnCheck = { ...encoder, id: 'c2', name: 'Tournament site', kind: 'http', host: '', url: 'https://tournament.example.com/',
  expect: '200-399', cert_warn_days: 14, slow_ms: 1000, status: 'warn', latency_ms: 90, code: 200, cert_days: 5, loss: null,
  note: 'The certificate ends in 5 days.' }
const data: ServicesData = { uplinks: [], resolvers: [], sites: [], checks: [encoder, site], lan_cache: null, interval: 30,
  last_poll: 2, via_agent: true, probe_ports: [53, 80, 443, 853], devices: [] }
const games: GameServerList = { servers: [], interval: 30, last_poll: 1, via_agent: true, counts: { up: 0, down: 0, unknown: 0 }, players: 0 }
const summary: ServiceSummary = {
  rows: [
    { id: 'check:c1', name: 'Stream encoder', kind: 'check', status: 'up', summary: '', link: '/services' },
    { id: 'dhcp-players', name: 'DHCP players', kind: 'dhcp', status: 'warn', summary: '24 of 120 leases left', link: '' },
    { id: 'http:wiki', name: 'Crew wiki', kind: 'web', status: 'up', summary: '200 OK', link: '' },
  ],
  total: 3, counts: { up: 2, warn: 1, down: 0, unknown: 0 }, by_kind: {},
  tags: { 'check:c1': ['Stage'], 'dhcp-players': ['Hall B', 'Stage'] },
}
const wall: HealthWall = {
  checks: [{ id: 'dhcp-players', name: 'DHCP players', kind: 'dhcp', status: 'warn', summary: '24 of 120 leases left', link: '',
    plugin: 'dhcp', plugin_name: 'DHCP', since: 1_763_100_000, muted_until: null,
    metrics: [{ label: 'Leases left', value: 24, unit: '', tone: 'warn' }],
    forecast: { used: 96, total: 120, pct: 80, rate_per_min: 0.6, full_in_min: 40, level: 'warn' } }],
  counts: { up: 0, warn: 1, down: 0, unknown: 0 }, last_poll: 1, interval: 30, plugins: 1,
}
const api = (extra: Record<string, unknown> = {}, me: unknown = lead) => fakeFetch({
  'GET /api/auth/me': me, 'GET /api/services': data, 'GET /api/game-servers': games, 'GET /api/services/summary': summary,
  'GET /api/health': wall, ...extra,
})

describe('Services with what Service health showed (#1337)', () => {
  it('lists own checks and plugin services once, with their tags', async () => {
    vi.stubGlobal('fetch', api({}, viewer).fn)
    renderWithApp(<Services />)
    const own = await screen.findByRole('region', { name: 'Own checks' })
    const enc = within(own).getByRole('group', { name: 'Stream encoder' })
    expect(within(enc).getByText('Ping · 192.0.2.40')).toBeInTheDocument()
    expect(within(enc).getByText('Stage')).toBeInTheDocument()
    expect(within(own).getByText(/Status 200 · certificate 5 days/)).toBeInTheDocument()
    // The plugin's HTTP check sits with the sites, the DHCP scope under DHCP; nothing twice.
    expect(within(screen.getByRole('region', { name: 'Internet sites' })).getByRole('group', { name: 'Crew wiki' })).toBeInTheDocument()
    expect(screen.getAllByRole('group', { name: 'Stream encoder' })).toHaveLength(1)
    expect(within(screen.getByRole('button', { name: 'Show: All' })).getByText('4')).toBeInTheDocument()
  })

  it('groups by tag: a service with two tags shows under both, one without under No tag', async () => {
    vi.stubGlobal('fetch', api().fn)
    renderWithApp(<Services />)
    await screen.findByRole('group', { name: 'Stream encoder' })
    fireEvent.click(screen.getByRole('button', { name: 'Group by: Type' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Tag' }))
    const stage = await screen.findByRole('region', { name: 'Stage' })
    expect(within(stage).getAllByRole('group').map((g) => g.getAttribute('aria-label'))).toEqual(['Stream encoder', 'DHCP players'])
    expect(within(screen.getByRole('region', { name: 'Hall B' })).getByRole('group', { name: 'DHCP players' })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'No tag' })).getByRole('group', { name: 'Tournament site' })).toBeInTheDocument()
  })

  it("opens a service's panel: the wall's numbers, the forecast, tags and mute", async () => {
    const fake = api({
      'POST /api/alerts/mutes': () => ({ status: 201, body: {} }),
      'POST /api/services/tags': (init?: RequestInit) => ({ body: { id: 'dhcp-players', tags: JSON.parse(String(init?.body)).tags } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Details of DHCP players' }))
    const panel = await screen.findByRole('complementary', { name: 'DHCP players: details' })
    expect(within(panel).getByText('Leases left')).toBeInTheDocument()
    expect(within(panel).getByText(/Full in about 40 minutes/)).toBeInTheDocument()
    expect(within(panel).getByText('From the DHCP server: set up in its plugin')).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: 'Mute alerts 1 h' }))
    await waitFor(() => expect(fake.calls.find((c) => c.path === '/api/alerts/mutes')?.body)
      .toEqual({ service_id: 'dhcp-players', minutes: 60 }))
    const tags = within(panel).getByLabelText('Tags')
    await userEvent.type(tags, 'Network{Enter}')
    await waitFor(() => expect(fake.calls.find((c) => c.path === '/api/services/tags')?.body)
      .toEqual({ id: 'dhcp-players', tags: ['Hall B', 'Stage', 'Network'] }))
  })

  it('adds an own HTTP(S) check after a test from the agent', async () => {
    const fake = api({
      'POST /api/services/checks/test': { status: 'up', latency_ms: 92, loss: null, code: 200, cert_days: 61, error: '' },
      'POST /api/services/checks': () => ({ status: 201, body: site }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add service' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Own check' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'Tournament site' } })
    fireEvent.click(screen.getByRole('radio', { name: 'HTTP(S)' }))
    fireEvent.change(screen.getByRole('textbox', { name: /^Address/ }), { target: { value: 'https://tournament.example.com/' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    expect(await screen.findByText('Up · Status 200 · 92 ms · certificate 61 days')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(fake.calls.find((c) => c.method === 'POST' && c.path === '/api/services/checks')?.body).toEqual({
      name: 'Tournament site', kind: 'http', slow_ms: 1000, url: 'https://tournament.example.com/', expect: '200-399', contains: '',
      cert_warn_days: 14,
    }))
  })

  it('has one Check now for everything', async () => {
    const fake = api({ 'POST /api/services/check': data })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(fake.calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/api/services/check']))
  })
})
