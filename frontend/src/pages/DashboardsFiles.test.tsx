import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Dashboards from './Dashboards'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

const editor = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.edit'] } }
const text = { x: 0, y: 0, w: 24, h: 3, node: { pane: { kind: 'text', text: 'Hello', size: 'm', align: 'start' } } }
const mine = { id: 'desk', name: 'Desk', fit: false, sections: [{ panels: [text] }] }
const shipped = { id: 'shelly-power', name: 'Power', fit: true, builtin: true, plugin: 'shelly', plugin_name: 'Shelly', sections: [{ panels: [text] }] }

describe('Dashboard files (#938)', () => {
  it('imports a dashboard file and says which plugins its tiles need', async () => {
    const api = fakeFetch({
      'GET /api/dashboards': { layouts: [mine, shipped] },
      'POST /api/dashboards/import': { layout: { ...mine, id: 'desk-2' }, missing: ['shelly'] },
      'GET /api/auth/me': editor,
    })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<Dashboards />, '/dashboards')
    expect(await screen.findByText('From Shelly')).toBeInTheDocument()
    const file = new File([JSON.stringify({ floorbit_dashboard: 1, name: 'Desk', sections: [] })], 'desk.dashboard.json', { type: 'application/json' })
    await screen.findByRole('button', { name: 'Import' })
    const input = container.ownerDocument.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toMatchObject({ floorbit_dashboard: 1, name: 'Desk' }))
    expect(await screen.findByText(/need plugins this Floorbit doesn’t have on: shelly/)).toBeInTheDocument()
  })

  it('exports a dashboard as saved from the editor menu', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dashboards': { layouts: [mine] }, 'GET /api/auth/me': editor }).fn)
    renderWithApp(<Dashboards />, '/dashboards?edit=desk')
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    const item = await screen.findByRole('menuitem', { name: 'Export as file' })
    expect(item).toHaveAttribute('href', '/api/dashboards/desk/export')
    expect(item).toHaveAttribute('download')
  })
})
