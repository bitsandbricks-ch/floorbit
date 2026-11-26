import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Applications from './Applications'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const none = { sites: [], ports: [], cidr: [], depots: [] }
const seen = { lookups: 40, dns_seats_max: 12, traffic_bytes: 2_000_000_000, traffic_seats: 30, cache_hit_bytes: null, cache_miss_bytes: null, players: 20, seats: 30 }
const app = (over: object) => ({
  id: 'x', name: 'X', kind: 'game', category: 'gaming', part_of: null, caches: [], source: 'floorbit', builtin: true,
  edited: false, hidden: false, redundant: false, added: none, seen: { ...seen, seats: 0, lookups: null, dns_seats_max: null, traffic_bytes: null, traffic_seats: null, players: null }, ...none, ...over,
})
const answer = {
  hours: 24, kinds: ['game', 'launcher', 'sitegroup'], categories: ['gaming'],
  sources: [{ id: 'cache-domains', repo: 'uklans/cache-domains', commit: 'f7d6206f47', license: 'MIT', copyright: '' }],
  synced: [], frozen: false, unrecognised: [] as { site: string; lookups: number; seats: number }[],
  applications: [
    app({ id: 'steam', name: 'Steam', kind: 'launcher', sites: ['steamcontent.com'], caches: ['steam'] }),
    app({ id: 'valorant', name: 'Valorant', part_of: 'riot', sites: ['example.net', 'playvalorant.com'], edited: true,
      added: { ...none, sites: ['example.net'] }, seen }),
    app({ id: 'riot', name: 'Riot Games', kind: 'launcher', sites: ['riotgames.com'] }),
    app({ id: 'streaming', name: 'Streaming', kind: 'sitegroup', sites: ['twitch.tv'] }),
  ],
}

describe('Applications', () => {
  it('lists games, launchers and site groups, busiest first, and filters by kind', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/applications?hours=24': answer }).fn)
    renderWithApp(<Applications />, '/applications')
    const first = await screen.findByText('Valorant')
    expect(first.closest('tr')).toHaveTextContent('built-in, changed')
    expect(screen.getByText('uklans/cache-domains (MIT, f7d6206)', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Streaming')).toBeInTheDocument()
  })

  it('shows what the event added to a built-in one beside the list, and saves it', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/applications?hours=24': answer,
      'PUT /api/applications/valorant': answer.applications[1],
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Applications />, '/applications')
    fireEvent.click(await screen.findByText('Valorant'))
    expect(await screen.findByText('Added for this event')).toBeInTheDocument()
    expect(screen.getByText('playvalorant.com')).toBeInTheDocument()     // built in: a fixed chip
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('button', { name: 'Hide' })).toBeInTheDocument()
    const put = fake.calls.find((c) => c.method === 'PUT')
    expect(put?.body).toEqual({ sites: ['example.net'], ports: [], cidr: [], depots: [], hidden: false, category: 'gaming' })
  })

  it('offers no changes to someone who may only look', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/applications?hours=24': answer }).fn)
    renderWithApp(<Applications />, '/applications')
    fireEvent.click(await screen.findByText('Valorant'))
    expect(await screen.findByText('Added for this event')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add application' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('lists what nothing recognises and makes an application from it', async () => {
    const withSites = { ...answer, unrecognised: [{ site: 'example.org', lookups: 300, seats: 12 }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/applications?hours=24': withSites }).fn)
    renderWithApp(<Applications />, '/applications')
    expect(await screen.findByText('Not recognised')).toBeInTheDocument()
    expect(screen.getByText('12 seats · 300 lookups')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Make an application' }))
    expect(await screen.findByText('example.org', { selector: '.mantine-TagsInput-pill *, .mantine-Pill-label' })).toBeInTheDocument()
  })

  it('offers to drop a local copy that Floorbit now ships', async () => {
    const shipped = { ...answer, applications: [{ ...answer.applications[1], redundant: true }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/applications?hours=24': shipped }).fn)
    renderWithApp(<Applications />, '/applications')
    fireEvent.click(await screen.findByText('Valorant'))
    expect(await screen.findByRole('button', { name: 'Drop the local copy' })).toBeInTheDocument()
  })
})
