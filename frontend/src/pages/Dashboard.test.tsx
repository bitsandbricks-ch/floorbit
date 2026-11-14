import { screen } from '@testing-library/react'
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
})
