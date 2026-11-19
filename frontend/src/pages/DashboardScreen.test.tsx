import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import DashboardScreen from './DashboardScreen'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

/** jsdom lays nothing out: give tile boxes a medium size, so a tile draws its rows. */
function layOut() {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(400)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(240)
}

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
    layOut()
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

  it('frames the screen with a header and the status line, unless the dashboard switches them off', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: true, board, tiles: {}, app: '1' },
      'GET /api/dashboards/kiosk': { ...board, name: 'Ops wall' },
      'GET /api/dashboards/traffic/public': { account: true, board: null, tiles: {}, app: '1' },
      'GET /api/dashboards/traffic': { ...board, id: 'traffic', name: 'Traffic' },
      'GET /api/tenant/events': { events: [{ id: 'e1', name: 'Autumn LAN', status: 'live' }], live: 'e1', current: 'e1' },
      'GET /api/problems': { counts: { down: 2, warn: 0 }, checked_at: 0, problems: [] },
      'GET /api/version': { app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Routes><Route path="/dashboards/:id" element={<DashboardScreen />} /></Routes>, '/dashboards/kiosk?rotate=kiosk,traffic')
    expect(await screen.findByText('Ops wall')).toBeInTheDocument()
    expect(await screen.findByText('Autumn LAN')).toBeInTheDocument()
    expect(await screen.findByText('Next: Traffic')).toBeInTheDocument()
    expect(await screen.findByRole('contentinfo', { name: 'Status' })).toBeInTheDocument()
  })

  it('leaves the frame off when the dashboard says so, and a public wall asks for nothing more', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: false, board: { ...board, frame: false }, tiles: {}, app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    show()
    expect(await screen.findByText('Welcome')).toBeInTheDocument()
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Time')).toBeInTheDocument()
  })

  it('makes a pane large in the dashboard area, and Esc goes back', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: false, board, tiles: { 'floorbit/w/down': 'Switches down' }, app: '1' },
      'GET /api/dashboards/kiosk/public/tiles/down': {
        id: 'down', type: 'list', items: [{ label: 'sw-a-01', value: '7 min', tone: 'err' }], sub: '', link: '',
      },
    })
    vi.stubGlobal('fetch', api.fn)
    layOut()
    show()
    ;(await screen.findByRole('button', { name: 'Make Switches down large' })).click()
    expect(await screen.findByRole('button', { name: 'Back to the dashboard' })).toBeInTheDocument()
    expect(screen.getByText('Goes back by itself in 60 s · Esc')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01')).toBeInTheDocument()
    expect(screen.queryByText('Welcome')).not.toBeInTheDocument()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(await screen.findByText('Welcome')).toBeInTheDocument()
  })

  it('calls attention to something down that nobody has taken yet', async () => {
    const down = (id: string, extra: object = {}) => ({ id, kind: 'switch', level: 'down', title: `${id} down`, where: 'Hall A', since: null, link: '', ...extra })
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: true, board, tiles: {}, app: '1' },
      'GET /api/dashboards/kiosk': board,
      'GET /api/problems': { counts: { down: 3, warn: 0, muted: 0 }, checked_at: 0, mutes: [], quiet_hours: false, can_mute: true, problems: [
        down('sw-a-01'), down('sw-b-02', { incident: 'i1' }), down('sw-c-03', { muted: { until: 0, by: null, reason: '' } }),
      ] },
      'GET /api/version': { app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    show()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('sw-a-01 down')
    // Taken (an incident) or muted: no call for attention.
    expect(alert).not.toHaveTextContent('sw-b-02')
    expect(alert).not.toHaveTextContent('sw-c-03')
  })

  it('keeps showing the board while the server is away, with a small note instead of a banner', async () => {
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: false, board, tiles: {}, app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    const { client } = show()
    expect(await screen.findByText('Welcome')).toBeInTheDocument()
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await client.refetchQueries()
    expect(await screen.findByText('No connection to the server: showing what was last read.')).toBeInTheDocument()
    expect(screen.getByText('Welcome')).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/)).not.toBeInTheDocument()
  })

  it('offers a crew member who may edit to make a scrolling dashboard fit the screen', async () => {
    let page = { ...board, fit: false, public: false }
    const editor = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.edit'] } }
    const api = fakeFetch({
      'GET /api/dashboards/kiosk/public': { status: 404, body: { error: 'not public' } },
      'GET /api/dashboards/kiosk': () => ({ body: page }),
      'PUT /api/dashboards/kiosk': (init: RequestInit | undefined) => ({ body: (page = { ...page, ...JSON.parse(String(init?.body)) }) }),
      'GET /api/auth/me': editor,
      'GET /api/version': { app: '1' },
    })
    vi.stubGlobal('fetch', api.fn)
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Make it a Screen' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toMatchObject({ fit: true, name: 'Kiosk', public: false }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Make it a Screen' })).not.toBeInTheDocument())
  })

  it('asks no one who can not edit', async () => {
    const page = { ...board, fit: false }
    const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: [] } }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: true, board: page, tiles: {}, app: '1' },
      'GET /api/dashboards/kiosk': page,
      'GET /api/auth/me': viewer,
      'GET /api/version': { app: '1' },
    }).fn)
    show()
    expect(await screen.findByText('Welcome')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make it a Screen' })).not.toBeInTheDocument()
  })

  it('stops asking on this screen once kept a Page', async () => {
    const page = { ...board, fit: false }
    const editor = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.edit'] } }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/dashboards/kiosk/public': { account: true, board: page, tiles: {}, app: '1' },
      'GET /api/dashboards/kiosk': page,
      'GET /api/auth/me': editor,
      'GET /api/version': { app: '1' },
    }).fn)
    localStorage.removeItem('fb.keepPage.kiosk')
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Keep it a Page' }))
    expect(screen.queryByRole('button', { name: 'Make it a Screen' })).not.toBeInTheDocument()
    expect(localStorage.getItem('fb.keepPage.kiosk')).toBe('1')
    localStorage.removeItem('fb.keepPage.kiosk')
  })
})
