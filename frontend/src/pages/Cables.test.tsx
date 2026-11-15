import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Cable, CableList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Cables from './Cables'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const base = { updated_at: 1_763_100_000, by: 'Ana', note: '' }
const mine: Cable = { ...base, id: 'c1', label: 'C-0001', switch: 'sw-a-01', port: 'Gi1/0/3', panel: 'PP-A', panel_port: '3', seat: 'A-3', color: 'blue', length_m: 2.5, source: 'floorbit' }
const nb: Cable = { ...base, id: 'c2', label: 'NB-7', switch: 'sw-b-02', port: 'Gi1/0/12', panel: '', panel_port: '', seat: 'B-14', color: '', length_m: null, source: 'import', plugin: 'NetBox' }
const data: CableList = { cables: [mine, nb], sources: ['NetBox'] }

describe('Cables', () => {
  it('lists cables, searches, and adds one', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/cables': data,
      'POST /api/cables': () => ({ status: 201, body: { ...mine, id: 'c3', label: 'C-0002' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    expect(await screen.findByText('C-0001')).toBeInTheDocument()
    expect(screen.getByText('PP-A 3')).toBeInTheDocument()
    expect(screen.getByText('Direct')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search label, switch, port, panel or seat' }), { target: { value: 'b-14' } })
    expect(screen.queryByText('C-0001')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Print labels' })).toHaveAttribute('href', '/api/cables/labels.pdf?q=b-14')

    fireEvent.click(screen.getByRole('button', { name: 'Add cable' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Switch port' }), { target: { value: 'Gi1/0/9' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Switch' }), { target: { value: 'sw-a-01' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Seat' }), { target: { value: 'A-9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/cables'
      && (c.body as { port: string; seat: string }).port === 'Gi1/0/9' && (c.body as { seat: string }).seat === 'A-9')).toBe(true))
  })

  it('imports from NetBox and shows what came back', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/cables': data,
      'POST /api/cables/import': { imported: 12, errors: ['1 cable(s) skipped'] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    fireEvent.click(await screen.findByRole('button', { name: 'Import from NetBox' }))
    expect(await screen.findByText('Imported 12 cables.')).toBeInTheDocument()
    expect(screen.getByText('1 cable(s) skipped')).toBeInTheDocument()
  })

  it('opens the cable a label links to, read-only for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/cables': data }).fn)
    renderWithApp(<Cables />, '/cables?cable=c2')
    expect(await screen.findByText('This cable comes from NetBox. Change it there and import again.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add cable' })).not.toBeInTheDocument()
  })
})
