import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FlowsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Traffic from './Traffic'
import { bytes, mostly } from './traffic/format'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const G = 1e9
const flows = (over: Partial<FlowsData> = {}): FlowsData => ({
  collector: true, can_see_seats: true, rules_error: null, updated: now, flows: 1200,
  mix_hour: { gaming: 60 * G, web: 30 * G, downloads: 10 * G }, mix_day: { gaming: 600 * G, web: 400 * G },
  series: [], areas: [{ area: 'A', bytes: 100 * G, mix: { gaming: 60 * G, web: 40 * G } }],
  services: [{ name: 'Steam', category: 'gaming', bytes: 500 * G, seats: 40 }], other_services: 2 * G,
  seats: [{ seat: 'A-12', area: 'A', bytes: 80 * G, mix: { gaming: 70 * G, web: 10 * G } }],
  anomalies: [{ id: 'p2p:D-5', kind: 'p2p', seat: 'D-5', area: 'D', title: 'P2P or torrent traffic from seat D-5',
    detail: '400 peers in one minute', first_seen: now - 600, last_seen: now }],
  min_seats: 5, retention_days: 7, raw: { files: 3, bytes: 1000, oldest: null }, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['seats.view'] } }

describe('Traffic', () => {
  it('formats volumes', () => {
    expect(bytes(80e9)).toBe('80.0 GB')
    expect(bytes(1.2e12)).toBe('1.2 TB')
    expect(bytes(512)).toBe('512 B')
    expect(mostly({ gaming: 1, web: 3 })).toBe('web')
  })

  it('shows the mix, areas, services, seats and anomalies', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/flows': flows() }).fn)
    renderWithApp(<Traffic />)
    expect(await screen.findByRole('img', { name: 'The whole hall: Gaming 60 %, Downloads 10 %, Web 30 %' })).toBeInTheDocument()
    expect(screen.getByText('Steam')).toBeInTheDocument()
    expect(screen.getByText(/once 5 different seats used it/)).toBeInTheDocument()
    const seats = screen.getByRole('table')
    expect(within(seats).getByRole('link', { name: 'A-12' })).toHaveAttribute('href', '/?seat=A-12')
    expect(within(seats).getByText(/mostly Gaming/)).toBeInTheDocument()
    expect(screen.getByText('P2P or torrent traffic from seat D-5')).toBeInTheDocument()
  })

  it('leaves the seats out without seats.view', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/flows': flows({ seats: null, can_see_seats: false }) }).fn)
    renderWithApp(<Traffic />)
    expect(await screen.findByText('Steam')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('explains the collector when none sends data', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/flows': { collector: false, can_see_seats: true, rules_error: null } }).fn)
    renderWithApp(<Traffic />)
    expect(await screen.findByText(/optional container/)).toBeInTheDocument()
  })
})
