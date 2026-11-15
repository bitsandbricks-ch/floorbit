import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Dashboard from './Dashboard'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: true, user: { username: 'viewer', display_name: 'Viewer', role: 'viewer' } }

describe('Dashboard page', () => {
  it('points admins to the plugins when there are no tiles', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/dashboard': { tiles: [] } }).fn)
    renderWithApp(<Dashboard />)
    expect(await screen.findByRole('link', { name: 'Open Settings > Plugins' })).toHaveAttribute('href', '/settings/plugins')
  })

  it('loads each widget tile and shows its errors in the tile', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({
        'GET /api/auth/me': me,
        'GET /api/dashboard': {
          tiles: [
            { plugin: 'p', plugin_name: 'Probe', id: 'a', label: 'Uplink', size: 'small', refresh: 60, url: '/api/plugins/p/widgets/a' },
            { plugin: 'p', plugin_name: 'Probe', id: 'b', label: 'Broken', size: 'small', refresh: 60, url: '/api/plugins/p/widgets/b' },
          ],
        },
        'GET /api/plugins/p/widgets/a': { id: 'a', type: 'stat', value: 940, unit: 'Mbit/s', tone: 'ok', sub: '', link: '/kiosk' },
        'GET /api/plugins/p/widgets/b': () => ({ status: 502, body: { error: 'upstream timed out' } }),
      }).fn,
    )
    renderWithApp(<Dashboard />)
    expect(await screen.findByText('940')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Details' })).toHaveAttribute('href', '/kiosk')
    expect(await screen.findByText('✕ upstream timed out')).toBeInTheDocument()
  })

  it('shows a saved layout and saves an edit of it', async () => {
    const tiles = [
      { plugin: 'p', plugin_name: 'Probe', id: 'a', label: 'Uplink', size: 'small', refresh: 60, url: '/api/plugins/p/widgets/a' },
      { plugin: 'p', plugin_name: 'Probe', id: 'b', label: 'DHCP leases', size: 'small', refresh: 60, url: '/api/plugins/p/widgets/b' },
    ]
    const ops = { id: 'ops', name: 'Ops desk', tiles: ['p/w/b'], columns: 2, updated_at: 1, by: 'lea' }
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: false },
      'GET /api/dashboard': { tiles },
      'GET /api/dashboard/layouts': { layouts: [ops] },
      'GET /api/plugins/p/widgets/a': { id: 'a', type: 'stat', value: 940, unit: 'Mbit/s', tone: 'ok', sub: '', link: '' },
      'GET /api/plugins/p/widgets/b': { id: 'b', type: 'stat', value: 412, unit: '', tone: 'ok', sub: '', link: '' },
      'PUT /api/dashboard/layouts/ops': { ...ops, tiles: ['p/w/b', 'p/w/a'] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Dashboard />, '/dashboard?layout=ops')
    expect(await screen.findByText('412')).toBeInTheDocument()
    expect(screen.queryByText('Uplink')).toBeNull()
    expect(screen.getByRole('link', { name: 'Full screen' })).toHaveAttribute('href', '/dashboard?layout=ops&screen=1')
    fireEvent.click(screen.getByRole('button', { name: 'Edit layout' }))
    fireEvent.click(screen.getByLabelText('Uplink · Probe'))
    fireEvent.click(screen.getByRole('button', { name: 'Save layout' }))
    await waitFor(() => expect(api.calls).toContainEqual({
      method: 'PUT', path: '/api/dashboard/layouts/ops', body: { name: 'Ops desk', tiles: ['p/w/b', 'p/w/a'], columns: 2 },
    }))
  })
})
