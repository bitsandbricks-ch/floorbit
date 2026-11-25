import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Dashboards from './Dashboards'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

const editor = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.edit'] } }
const text = { x: 0, y: 0, w: 24, h: 3, node: { pane: { kind: 'text', text: 'Hello', size: 'm', align: 'start' } } }
const board = (over: Record<string, unknown>) => ({ fit: false, sections: [{ panels: [text] }], ...over })
const boards = [
  board({ id: 'noc', name: 'NOC wall', fit: true, tags: ['noc', 'wall'], group: 'Network crew', screens: 2, by: 'ana', updated_at: 1_790_000_000 }),
  board({ id: 'kiosk', name: 'Kiosk', public: true, builtin: true }),
  board({ id: 'hall-a', name: 'Hall A overview', tags: ['hall-a'], group: 'Floor crew', by: 'jo' }),
]

describe('Dashboards list', () => {
  it('lists every dashboard in one table with where it shows', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards': { layouts: boards }, 'GET /api/auth/me': editor }).fn)
    renderWithApp(<Dashboards />, '/dashboards')
    const table = await screen.findByRole('table', { name: 'Dashboards' })
    const noc = within(table).getByRole('link', { name: 'NOC wall' }).closest('tr')!
    expect(within(noc).getByText('2 screen accounts')).toBeInTheDocument()
    expect(within(noc).getByText('Network crew')).toBeInTheDocument()
    const kiosk = within(table).getByRole('link', { name: 'Kiosk' }).closest('tr')!
    expect(within(kiosk).getAllByText('Public').length).toBeGreaterThan(0)
    expect(within(table).getByRole('link', { name: 'Hall A overview' }).closest('tr')).toHaveTextContent('Inside the app')
  })

  it('searches names, tags and groups, and a tag filters the list', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards': { layouts: boards }, 'GET /api/auth/me': editor }).fn)
    renderWithApp(<Dashboards />, '/dashboards')
    await screen.findByRole('table', { name: 'Dashboards' })
    fireEvent.change(screen.getByRole('textbox', { name: /Search dashboards/ }), { target: { value: 'floor crew' } })
    await waitFor(() => expect(screen.queryByRole('link', { name: 'NOC wall' })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Hall A overview' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: /Search dashboards/ }), { target: { value: '' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Show dashboards tagged wall' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Kiosk' })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'NOC wall' })).toBeInTheDocument()
  })

  it('pins a dashboard to the sidebar from its row', async () => {
    localStorage.removeItem('floorbit-nav-prefs')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards': { layouts: boards }, 'GET /api/auth/me': editor }).fn)
    renderWithApp(<Dashboards />, '/dashboards')
    const pin = await screen.findByRole('button', { name: 'Pin to sidebar: Kiosk' })
    expect(pin).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(pin)
    expect(await screen.findByRole('button', { name: /Kiosk/, pressed: true })).toBeInTheDocument()
  })
})
