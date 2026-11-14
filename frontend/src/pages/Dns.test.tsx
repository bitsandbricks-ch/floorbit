import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DnsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Dns from './Dns'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const site = (name: string, category: DnsData['sites'][number]['category'], lookups: number, blocked = 0) =>
  ({ site: name, category, lookups, blocked, clients_max: 40 })
const dns = (over: Partial<DnsData> = {}): DnsData => ({
  hours: [{ t: now - 3600, lookups: 900, blocked: 50 }, { t: now, lookups: 1200, blocked: 70 }],
  lookups: 2100, blocked: 120, block_share: 0.0571,
  sites: [site('steamcontent.com', 'gaming', 700), site('doubleclick.net', 'other', 120, 120)],
  categories: [{ id: 'gaming', lookups: 700 }, { id: 'streaming', lookups: 0 }, { id: 'social', lookups: 0 },
    { id: 'updates', lookups: 0 }, { id: 'other', lookups: 120 }],
  unnamed_lookups: 1280, new: [{ ...site('new-game.example', 'other', 30), first_seen: now }],
  blocked_sites: [site('doubleclick.net', 'other', 120, 120)],
  min_clients: 5, plugins: 1, last_poll: now, error: null, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: [] } }

describe('Dns', () => {
  it('shows the hours, top sites, categories, blocked and new sites', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/dns?hours=24': dns() })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Dns />)
    expect(await screen.findByRole('img', { name: 'Lookups per hour: 2,100 in all, 120 blocked' })).toBeInTheDocument()
    expect(screen.getByText('5.7 % of all lookups')).toBeInTheDocument()
    expect(screen.getByText('steamcontent.com')).toBeInTheDocument()
    expect(screen.getAllByText('700')).toHaveLength(2)   // the site and its category
    expect(screen.getAllByText('up to 40 seats an hour')).toHaveLength(2)
    expect(screen.getAllByText('doubleclick.net')).toHaveLength(2)
    expect(screen.getByText('new-game.example')).toBeInTheDocument()
    expect(screen.getByText(/only named once 5 different seats/)).toBeInTheDocument()
  })

  it('explains the plugin when nothing sends lookups', async () => {
    const empty = dns({ plugins: 0, lookups: 0, blocked: 0, sites: [], new: [], blocked_sites: [] })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/dns?hours=24': empty }).fn)
    renderWithApp(<Dns />)
    expect(await screen.findByText(/A DNS plugin reads them/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'docs/dns.md' })).toBeInTheDocument()
  })
})
