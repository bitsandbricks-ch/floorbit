import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Dashboards from './Dashboards'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

const editor = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.edit'] } }
const text = { x: 0, y: 0, w: 24, h: 3, node: { pane: { kind: 'text', text: 'Hello', size: 'm', align: 'start' } } }
const kiosk = { id: 'kiosk', name: 'Kiosk', fit: true, public: true, changed: true, sections: [{ panels: [text] }] }

describe('Dashboards', () => {
  it('resets a changed ready-made dashboard after asking once', async () => {
    const api = fakeFetch({
      'GET /api/dashboards': { layouts: [kiosk] },
      'DELETE /api/dashboards/kiosk': { ok: true },
      'GET /api/auth/me': editor,
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Dashboards />, '/dashboards?edit=kiosk')
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Reset to default' }))
    expect(api.calls.some((c) => c.method === 'DELETE')).toBe(false)
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument()
    const dialog = await screen.findByRole('dialog', { name: /Reset Kiosk to its default/ })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reset to default' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'DELETE' && c.path === '/api/dashboards/kiosk')).toBe(true))
  })

  it('makes a copy of its own, not public, under a free id', async () => {
    const api = fakeFetch({
      'GET /api/dashboards': { layouts: [kiosk, { ...kiosk, id: 'kiosk-copy', changed: false, name: 'Kiosk (copy)' }] },
      'PUT /api/dashboards/kiosk-copy-2': (init: RequestInit | undefined) => ({ body: { id: 'kiosk-copy-2', ...JSON.parse(String(init?.body)) } }),
      'GET /api/auth/me': editor,
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Dashboards />, '/dashboards?edit=kiosk')
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Make a copy' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toMatchObject({ name: 'Kiosk (copy)', public: false, fit: true }))
    expect(api.calls.find((c) => c.method === 'PUT')?.path).toBe('/api/dashboards/kiosk-copy-2')
  })

  it('says in the settings how the picked pane draws at its size', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(400)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(240)
    const tile = { x: 0, y: 0, w: 8, h: 6, node: { pane: { kind: 'tile', tile: 'floorbit/w/down' } } }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/dashboards': { layouts: [{ ...kiosk, changed: false, sections: [{ panels: [tile] }] }] },
      'GET /api/dashboard': { tiles: [{ plugin: 'floorbit', plugin_name: 'Floorbit', id: 'down', label: 'Switches down', size: 'small', refresh: 15, url: '/api/dashboard/floorbit/down' }] },
      'GET /api/dashboard/floorbit/down': { id: 'down', type: 'list', items: [{ label: 'sw-a-01', value: '7 min', tone: 'err' }], sub: '', link: '' },
      'GET /api/auth/me': editor,
    }).fn)
    renderWithApp(<Dashboards />, '/dashboards?edit=kiosk')
    expect(await screen.findByText(/^Draws as (Small|Medium|Large) at this size\./)).toBeInTheDocument()
  })

  it('keeps the dashboard settings in a popover and floats the widget settings over the canvas', async () => {
    localStorage.removeItem('floorbit.boardPanelDocked')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards': { layouts: [kiosk] }, 'GET /api/auth/me': editor }).fn)
    renderWithApp(<Dashboards />, '/dashboards?edit=kiosk')
    // The first widget starts picked: its settings float over the canvas.
    const panel = await screen.findByRole('complementary', { name: 'Pane settings' })
    expect(panel).toHaveClass('is-float')
    expect(screen.queryByRole('switch', { name: /Public/ })).not.toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('toolbar', { name: 'Dashboard editor' })).getByRole('button', { name: 'Dashboard settings' }))
    expect(await screen.findByRole('switch', { name: /Public/ })).toBeChecked()
    // Docked beside the canvas, remembered; closing a floating panel hides it.
    fireEvent.click(screen.getByRole('button', { name: 'Dock beside the dashboard' }))
    expect(screen.getByRole('complementary', { name: 'Pane settings' })).toHaveClass('is-docked')
    expect(localStorage.getItem('floorbit.boardPanelDocked')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'Float over the dashboard' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close the widget settings' }))
    expect(screen.queryByRole('complementary', { name: 'Pane settings' })).not.toBeInTheDocument()
  })
})
