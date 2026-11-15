import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GamesData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Games from './Games'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const G = 1e9
const games = (over: Partial<GamesData> = {}): GamesData => ({
  launchers: [
    { id: 'steam', name: 'Steam', lookups: 4200, dns_seats_max: 60, traffic_bytes: 300 * G, traffic_seats: 55,
      cache_hit_bytes: 800 * G, cache_miss_bytes: 200 * G },
    { id: 'riot', name: 'Riot Games', lookups: 900, dns_seats_max: 20, traffic_bytes: null, traffic_seats: null,
      cache_hit_bytes: null, cache_miss_bytes: null },
  ],
  games: [{ name: 'Tournament servers', bytes: 40 * G, seats: 12 }],
  other_caches: [{ cache: 'wsus', hit_bytes: 30 * G, miss_bytes: 10 * G, requests: 900 }],
  cache: { configured: true, demo: false, hours: [{ t: now, hit_bytes: 800 * G, miss_bytes: 200 * G }],
    hit_bytes: 830 * G, miss_bytes: 210 * G, hit_ratio: 0.798, caches: [], last_read: now, error: null },
  sources: { dns: true, traffic: true, cache: true },
  min_seats: { dns: 5, traffic: 5 }, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: [] } }

describe('Games', () => {
  it('shows the cache, the launchers, the games and the other caches', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/games?hours=24': games() }).fn)
    renderWithApp(<Games />)
    expect(await screen.findByText('830 GB')).toBeInTheDocument()
    expect(screen.getByText('80 %')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'LAN cache per hour: 830 GB from the cache, 210 GB from the internet' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Steam' })).toBeInTheDocument()
    expect(screen.getByText('1.0 TB')).toBeInTheDocument()
    expect(screen.getByText('Tournament servers')).toBeInTheDocument()
    expect(screen.getByText('Windows Update')).toBeInTheDocument()
  })

  it('explains the sources when there are none', async () => {
    const none = games({ launchers: [], games: [], other_caches: [], sources: { dns: false, traffic: false, cache: false } })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/games?hours=24': none }).fn)
    renderWithApp(<Games />)
    expect(await screen.findByText(/Nothing to show yet/)).toBeInTheDocument()
  })
})
