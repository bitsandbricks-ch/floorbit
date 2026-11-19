import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LancacheOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import LancacheView from './LancacheView'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const now = Date.now() / 1000
const GB = 1024 ** 3
const data: LancacheOverview = {
  configured: true, demo: false, plugin_on: true, last_read: now, error: null,
  hours: [{ t: 1_794_000_000, hit_bytes: 30 * GB, miss_bytes: 10 * GB }],
  hit_bytes: 30 * GB, miss_bytes: 10 * GB, hit_ratio: 0.75, saved_bytes: 30 * GB,
  caches: [{ cache: 'steam', hit_bytes: 30 * GB, miss_bytes: 8 * GB, requests: 900 }],
  agents: [{
    id: 'a1', name: 'Hall agent', updated: now - 20, stale: false,
    disk: { used: 800 * GB, total: 1000 * GB, free: 200 * GB },
    heartbeat: { ok: true, ms: 3, processed_by: 'cache-01' },
    dns_check: { ok: false, error: 'the DNS server sends lancache.steamcontent.com somewhere else than the cache' },
    clearing: null, health: null,
  }],
  downloads: [{ cache: 'steam', item: 'depot 228988', hit_bytes: 6 * GB, miss_bytes: GB, requests: 60, clients: 12, hit_ratio: 0.857 }],
  other_downloads: { hit_bytes: 0, miss_bytes: GB, requests: 5, items: 3 },
  suspects: [{ cache: 'blizzard', item: 'tpr/wow', files: 1, misses: 3 }],
  dns_services: [{ cache: 'steam', lookups: 1500 }],
  clients: [{ t: 1_794_000_000, clients: 42 }],
  min_clients: 5, window_hours: 24,
}

describe('LancacheView', () => {
  it('shows what the cache saved, the machine and what the hall downloads, and clears it after asking', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/lancache?hours=24': data,
      'POST /api/plugins/lancache/actions/clear_cache': { ok: true, message: 'Clearing the cache. It fills again as players download.', data: {} },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<LancacheView expanded />)
    expect(await screen.findByText('75 %')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('answers (cache-01, 3 ms)')).toBeInTheDocument()
    expect(screen.getByText(/somewhere else than the cache/)).toBeInTheDocument()
    expect(screen.getByText(/of .* \(80 %\)/)).toBeInTheDocument()
    expect(screen.getByText('depot 228988')).toBeInTheDocument()
    expect(screen.getByText(/3 other downloads/)).toBeInTheDocument()
    expect(screen.getByText('tpr/wow')).toBeInTheDocument()
    expect(screen.getByText('3 misses')).toBeInTheDocument()
    expect(screen.getByText('1,500')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Clear the cache' }))
    expect(api.calls.some((c) => c.path.includes('clear_cache'))).toBe(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    expect(await screen.findByText(/It fills again/)).toBeInTheDocument()
  })

  it('says when the plugin is off', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/lancache?hours=24': { ...data, plugin_on: false, agents: [], downloads: [], suspects: [], dns_services: [] },
    }).fn)
    renderWithApp(<LancacheView expanded={false} />)
    expect(await screen.findByText(/The LAN cache plugin is off/)).toBeInTheDocument()
    expect(screen.getByText(/No agent has reported/)).toBeInTheDocument()
  })

  it('points to the Marketplace when the plugin is not installed', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/lancache?hours=24': { ...data, plugin_on: false, plugin_installed: false, agents: [], downloads: [], suspects: [], dns_services: [] },
    }).fn)
    renderWithApp(<LancacheView expanded={false} />)
    expect(await screen.findByText(/The LAN cache plugin is not installed/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Marketplace' })).toHaveAttribute('href', '/settings/plugins?tab=marketplace')
  })

  it('keeps clearing for the expanded view', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/lancache?hours=24': data }).fn)
    renderWithApp(<LancacheView expanded={false} />)
    expect(await screen.findByText('75 %')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Clear the cache' })).not.toBeInTheDocument()
    expect(screen.queryByText('depot 228988')).not.toBeInTheDocument()
  })
})
