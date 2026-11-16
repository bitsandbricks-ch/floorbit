import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BlockPlan, Cable, CableList } from '@/api/types'
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

  it('patches a whole block after a preview, and asks before replacing cables in the way', async () => {
    const cables = Array.from({ length: 16 }, (_, n) => ({ seat: `A-${n + 1}`, switch: 'sw-a-01', port: `Gi1/0/${n + 1}`, block: 'b1' }))
    const plan: BlockPlan = { block: 'A', cables, clashes: [{ seat: 'A-3', port: 'Gi1/0/3', kind: 'port', cable: 'C-0001', other_seat: 'B-9', imported: false }] }
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/cables': data, 'GET /api/switches': [{ id: 's1', name: 'sw-a-01' }],
      'GET /api/seat-blocks': [{ id: 'b1', name: 'A', cols: 8, rows: 2, hall_id: 'h' }],
      'POST /api/cables/block': (init?: RequestInit) => ({
        body: JSON.parse(String(init?.body)).dry_run ? plan : { ...plan, created: 16, removed: 1 } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    fireEvent.click(await screen.findByRole('button', { name: 'Patch a block' }))
    fireEvent.click(await screen.findByRole('combobox', { name: 'Seat block' }))
    fireEvent.click(await screen.findByRole('option', { name: 'A (16)', hidden: true }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Switch' }), { target: { value: 'sw-a-01' } })
    expect(await screen.findByText('16 seats get a cable:')).toBeInTheDocument()
    expect(screen.getByText('… A-16')).toBeInTheDocument()                      // a long block is cut short
    expect(screen.getByText('Gi1/0/3 already has cable C-0001 to seat B-9.')).toBeInTheDocument()
    const make = screen.getByRole('button', { name: 'Make 16 cables' })
    expect(make).toBeDisabled()                                                   // not without saying so
    fireEvent.click(screen.getByRole('checkbox', { name: 'Replace the cables in the way' }))
    await waitFor(() => expect(make).toBeEnabled())
    fireEvent.click(make)
    expect(await screen.findByText('Made 16 cables, replaced 1.')).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.path === '/api/cables/block').map((c) => c.body as Record<string, unknown>)
    expect(sent[0]).toMatchObject({ block: 'b1', switch: 'sw-a-01', first_port: 'Gi1/0/1', order: 'rows', dry_run: true })
    expect(sent.filter((b) => !b.dry_run)).toEqual([expect.objectContaining({ block: 'b1', replace: true })])
  })

  it('checks the plan against the ports the network reports', async () => {
    const list = (rows: object[]) => ({ count: rows.length, rows })
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': viewer, 'GET /api/cables': data,
      'GET /api/cables/check': {
        last_poll: 1_763_100_000, blocks: [{ block: 'b1', name: 'A', seats: 24, up: 18 }],
        missing: list([{ seat: 'A-4', switch: 'sw-a-01', port: 'Gi1/0/40' }]),
        conflicts: list([{ seat: 'A-1', switch: 'sw-a-01', port: 'Gi1/0/1', described_seat: 'A-2' }]),
        unplanned: list([{ switch: 'sw-a-01', port: 'Gi1/0/30' }]),
        down: list([{ seat: 'A-7', switch: 'sw-a-01', port: 'Gi1/0/7' }]), unread: ['sw-z-09'],
      },
    }).fn)
    renderWithApp(<Cables />)
    expect(await screen.findByText('18 of 24 seat ports up')).toBeInTheDocument()
    expect(screen.getByText("1 cable names a port the switch doesn't have")).toBeInTheDocument()
    expect(screen.getByText('A-4: sw-a-01 Gi1/0/40')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 Gi1/0/1: cable says A-1, the switch says A-2')).toBeInTheDocument()
    expect(screen.getByText('1 port is up and no cable says what is on it')).toBeInTheDocument()
    expect(screen.getByText('1 seat port not up yet: A-7')).toBeInTheDocument()
    expect(screen.getByText('Not read (not on the floor plan, or offline): sw-z-09')).toBeInTheDocument()
  })
})
