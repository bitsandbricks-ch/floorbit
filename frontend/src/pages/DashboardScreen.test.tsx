import { screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import DashboardScreen from './DashboardScreen'

afterEach(() => vi.unstubAllGlobals())

const panel = (x: number, pane: object) => ({ x, y: 0, w: 8, h: 12, node: { pane } })
const board = {
  id: 'kiosk', name: 'Kiosk', fit: true, public: true, sections: [{ panels: [
    panel(0, { kind: 'tile', tile: 'floorbit/w/down' }),
    panel(8, { kind: 'private', title: 'Crew' }),
    panel(16, { kind: 'text', text: 'Welcome', size: 'm', align: 'start' }),
  ] }],
}

const show = () => renderWithApp(<Routes><Route path="/dashboards/:id" element={<DashboardScreen />} /></Routes>, '/dashboards/kiosk')

describe('Dashboard screen', () => {
  it('reads a public dashboard from its open feed when nobody is signed in', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: false, board, tiles: { 'floorbit/w/down': 'Switches down' }, app: '1' },
      'GET /api/dashboards/kiosk/public/tiles/down': {
        id: 'down', type: 'list', items: [{ label: 'sw-a-01', value: '7 min', tone: 'err' }], sub: '', link: '',
      },
    })
    vi.stubGlobal('fetch', api.fn)
    show()
    expect(await screen.findByText('sw-a-01')).toBeInTheDocument()
    expect(screen.getByText('Switches down')).toBeInTheDocument()
    expect(screen.getByText('Needs an account: not shown on a public screen.')).toBeInTheDocument()
    expect(screen.getByText('Welcome')).toBeInTheDocument()
    // Nothing that needs an account: that would send the screen to the sign-in page.
    expect(api.calls.map((c) => c.path).filter((p) => !p.startsWith('/api/dashboards/kiosk/public') && p !== '/api/events')).toEqual([])
  })

  it('reads the full dashboard when signed in', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: true, board, tiles: {}, app: '1' },
      'GET /api/dashboards/kiosk': { ...board, sections: [{ panels: [panel(0, { kind: 'text', text: 'Crew wall', size: 'm', align: 'start' })] }] },
      'GET /api/version': { app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    show()
    expect(await screen.findByText('Crew wall')).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/dashboards/kiosk')).toBe(true))
  })
})
