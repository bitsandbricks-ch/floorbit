import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import ViewPage from './ViewPage'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }

const empty = {
  configured: true, demo: false, plugin_on: true, last_read: null, error: null, hours: [], hit_bytes: 0, miss_bytes: 0,
  hit_ratio: null, saved_bytes: 0, caches: [], agents: [], downloads: [], other_downloads: { hit_bytes: 0, miss_bytes: 0, requests: 0, items: 0 },
  suspects: [], dns_services: [], clients: [], min_clients: 5, window_hours: 24,
}

describe('ViewPage', () => {
  it('shows a Monitoring view at its big size under the page title and intro', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/lancache?hours=24': empty })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<ViewPage view="lancache" />, '/lancache')
    expect((await screen.findAllByRole('heading', { name: 'LAN cache' })).length).toBeGreaterThan(0)
    expect(screen.getByText(/What the LAN cache saved/)).toBeInTheDocument()
    await vi.waitFor(() => expect(api.calls.some((c) => c.path.startsWith('/api/lancache'))).toBe(true))
  })
})
