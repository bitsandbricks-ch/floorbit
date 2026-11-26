import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BlockPlan, Cable, CableList } from '@/api/types'
import { OPTIONS, pick } from '@/test/options'
import { Route, Routes } from 'react-router-dom'
import { fakeFetch, renderWithApp } from '@/test/render'
import Cables from './Cables'
import CablePage from './cables/CablePage'

// The list and a cable's own page, so a click from one lands on the other.
const app = (route = '/cables') => renderWithApp(
  <Routes>
    <Route path="/cables" element={<Cables />} />
    <Route path="/cables/:id" element={<CablePage />} />
  </Routes>, route)

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const base = { updated_at: 1_763_100_000, by: 'Ana', note: '' }
const mine: Cable = { ...base, id: 'c1', label: 'C-0001', switch: 'sw-a-01', port: 'Gi1/0/3', panel: 'PP-A', panel_port: '3', seat: 'A-3', color: 'blue', length_m: 2.5, source: 'floorbit' }
const nb: Cable = { ...base, id: 'c2', label: 'NB-7', switch: 'sw-b-02', port: 'Gi1/0/12', panel: '', panel_port: '', seat: 'B-14', color: '', length_m: null, source: 'import', plugin: 'NetBox' }
const data: CableList = { cables: [mine, nb], sources: ['NetBox'] }

describe('Cables', () => {
  it('lists cables that each open their own page, and searches', async () => {
    vi.stubGlobal('fetch', fakeFetch({ ...OPTIONS, 'GET /api/auth/me': lead, 'GET /api/cables': data }).fn)
    app()
    expect(await screen.findByRole('link', { name: 'C-0001' })).toHaveAttribute('href', '/cables/c1')
    expect(screen.getByText('PP-A 3')).toBeInTheDocument()
    expect(screen.getByText('Direct')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add cable' })).toHaveAttribute('href', '/cables/new')
    fireEvent.change(screen.getByRole('textbox', { name: 'Search label, switch, port, panel or seat' }), { target: { value: 'b-14' } })
    expect(screen.queryByText('C-0001')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'More' }))
    expect(await screen.findByRole('menuitem', { name: 'Print labels' })).toHaveAttribute('href', '/api/cables/labels.pdf?q=b-14')
    // Add cable is the one button; the walk-through sits in More so a phone shows the head whole (#1044).
    expect(screen.queryByRole('link', { name: 'Walk the row' })).toBeNull()
    expect(screen.getByText('Walk the row').closest('a')).toHaveAttribute('href', '/cables/walk')
  })

  it('adds a cable on its own page, then shows the saved cable there', async () => {
    const saved = { ...mine, id: 'c3', label: 'C-0002', port: 'Gi1/0/9', seat: 'A-9' }
    let made = false
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': lead,
      'GET /api/cables': () => ({ body: { ...data, cables: made ? [mine, nb, saved] : data.cables } }),
      'POST /api/cables': () => { made = true; return { status: 201, body: saved } },
    })
    vi.stubGlobal('fetch', api.fn)
    app('/cables/new')
    await pick('Switch', 'sw-a-01')
    // Only free ports: Gi1/0/3 has a cable to A-3, so it isn't offered.
    fireEvent.click(await screen.findByRole('combobox', { name: 'Switch port' }))
    expect(await screen.findByRole('option', { name: 'Gi1/0/2', hidden: true })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Gi1/0/3', hidden: true })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'Gi1/0/9', hidden: true }))
    await pick('Seat', 'A-9')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/cables'
      && (c.body as { port: string; seat: string }).port === 'Gi1/0/9' && (c.body as { seat: string }).seat === 'A-9')).toBe(true))
    expect((await screen.findAllByRole('heading', { name: 'C-0002' })).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Print its labels' })).toHaveAttribute('href', '/api/cables/labels.pdf?ids=c3')
  })

  it('imports from NetBox and shows what came back', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/cables': data,
      'POST /api/cables/import': { imported: 12, errors: ['1 cable(s) skipped'] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    // One import for every source, which the item names below it (issue #880).
    const item = await screen.findByRole('menuitem', { name: /^Import cables/ })
    expect(item).toHaveTextContent('From NetBox')
    fireEvent.click(item)
    expect(await screen.findByText('Imported 12 cables.')).toBeInTheDocument()
    expect(screen.getByText('1 cable(s) skipped')).toBeInTheDocument()
  })

  it('opens the cable a label links to, read-only for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/cables': data }).fn)
    app('/cables/c2')
    expect(await screen.findByText('This cable comes from NetBox. Change it there and import again.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('says so when a cable is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/cables': data }).fn)
    app('/cables/c9')
    expect(await screen.findByText('This cable is gone.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'All cables' })).toHaveAttribute('href', '/cables')
  })

  it('patches rows after a preview, and asks before replacing cables in the way', async () => {
    const cables = Array.from({ length: 16 }, (_, n) => ({ seat: `A-${n + 1}`, switch: 'sw-a-01', port: `Gi1/0/${n + 1}`, block: 'b1' }))
    const plan: BlockPlan = { rows: ['A 1', 'A 2'], cables, clashes: [{ seat: 'A-3', port: 'Gi1/0/3', kind: 'port', cable: 'C-0001', other_seat: 'B-9', imported: false }] }
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': lead, 'GET /api/cables': data,
      'POST /api/cables/block': (init?: RequestInit) => ({
        body: JSON.parse(String(init?.body)).dry_run ? plan : { ...plan, created: 16, removed: 1 } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Patch rows' }))
    await pick('Rows', 'A 1 (8 seats)')
    await pick('Rows', 'A 2 (8 seats)')
    await pick('Switch', 'sw-a-01')
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
    expect(sent[0]).toMatchObject({ rows: ['b1:1', 'b1:2'], switch: 'sw-a-01', first_port: 'Gi1/0/1', order: 'rows', dry_run: true })
    expect(sent.filter((b) => !b.dry_run)).toEqual([expect.objectContaining({ rows: ['b1:1', 'b1:2'], replace: true })])
  })

  it('checks the plan against the ports the network reports', async () => {
    const list = (rows: object[]) => ({ count: rows.length, rows })
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': viewer, 'GET /api/cables': data,
      'GET /api/cables/check': {
        last_poll: 1_763_100_000, rows: [{ row: 'b2:1', name: 'C', block_label: 'C\u2013D', naming: 'rows', seats: 24, up: 18 }],
        missing: list([{ seat: 'A-4', switch: 'sw-a-01', port: 'Gi1/0/40' }]),
        conflicts: list([{ seat: 'A-1', switch: 'sw-a-01', port: 'Gi1/0/1', described_seat: 'A-2' }]),
        unplanned: list([{ switch: 'sw-a-01', port: 'Gi1/0/30' }]),
        down: list([{ seat: 'A-7', switch: 'sw-a-01', port: 'Gi1/0/7' }]), unread: ['sw-z-09'],
      },
    }).fn)
    renderWithApp(<Cables />, '/cables?tab=check')   // issue #880: the check is a tab of its own
    expect(await screen.findByText('18 of 24 seat ports up')).toBeInTheDocument()
    expect(screen.getByText("1 cable names a port the switch doesn't have")).toBeInTheDocument()
    expect(screen.getByText('A-4: sw-a-01 Gi1/0/40')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 Gi1/0/1: cable says A-1, the switch says A-2')).toBeInTheDocument()
    expect(screen.getByText('1 port is up and no cable says what is on it')).toBeInTheDocument()
    expect(screen.getByText('1 seat port not up yet: A-7')).toBeInTheDocument()
    expect(screen.getByText('Not read (not on the floor plan, or offline): sw-z-09')).toBeInTheDocument()
  })

  it('lists machines on ports the cables do not explain, and patches one to a seat', async () => {
    const crew = { ...lead, user: { ...lead.user, permissions: ['floorplan.view', 'floorplan.edit', 'seats.view'] } }
    const clients = {
      as_of: 1_763_100_000, reading: false, started: false, error: null, switches: 3, clients: 120,
      failed: [{ switch: 'sw-c-03', error: 'timeout' }],
      moved: { count: 1, rows: [{ switch: 'sw-a-01', port: 'Gi1/0/2', mac: '02:00:00:00:00:03', ip: '192.0.2.13', ip_seat: 'A-3', seat: 'A-2', cable: 'C-0002' }] },
      unplanned: { count: 1, rows: [{ switch: 'sw-a-01', port: 'Gi1/0/30', mac: '02:00:00:00:00:30', ip: '192.0.2.40', ip_seat: 'A-9' }] },
      shared: { count: 2, rows: [
        { switch: 'sw-a-01', port: 'Gi1/0/5', seat: 'A-5', cable: 'C-0005', macs: 6, desk_switch: true },
        { switch: 'sw-a-01', port: 'Gi1/0/6', seat: 'A-6', cable: 'C-0006', macs: 2, desk_switch: false },
      ] },
      no_port: { count: 1, rows: [{ mac: '02:00:00:00:00:50', ip: '192.0.2.50', ip_seat: '' }] },
      empty: { count: 2, rows: [{ seat: 'A-4', switch: 'sw-a-01', port: 'Gi1/0/4' }, { seat: 'A-5', switch: 'sw-a-01', port: 'Gi1/0/5' }] },
      ignored: 1,
    }
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': crew, 'GET /api/cables': data, 'GET /api/cables/clients?read=1': clients,
      'POST /api/cables': () => ({ status: 201, body: { ...mine, id: 'c4' } }),
      'POST /api/cables/clients/ignored': { ok: true },
    })
    vi.stubGlobal('fetch', api.fn)
    app('/cables?tab=check')
    expect(await screen.findByText('1 machine on another seat\'s port')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 Gi1/0/2 is cabled to A-2, but 192.0.2.13 is the IP of A-3')).toBeInTheDocument()
    expect(screen.getByText('1 machine on a port no cable explains')).toBeInTheDocument()
    expect(screen.getByText('No MAC table from: sw-c-03')).toBeInTheDocument()
    // More than one machine on a seat port: how many, and a router or switch at the seat marked.
    expect(screen.getByText('2 seat ports with more than one machine')).toBeInTheDocument()
    expect(screen.getByText('6 machines')).toBeInTheDocument()
    expect(screen.getAllByText('Switch or router at the seat')).toHaveLength(1)
    // Issue #949: PCs that never check in.
    expect(screen.getByText('1 IP in the seat networks on no seat port')).toBeInTheDocument()
    expect(screen.getByText('192.0.2.50 · 02:00:00:00:00:50')).toBeInTheDocument()
    expect(screen.getByText('2 seats cabled to a port with no machine')).toBeInTheDocument()
    expect(screen.getByText('A-4 (sw-a-01 Gi1/0/4), A-5 (sw-a-01 Gi1/0/5)')).toBeInTheDocument()
    expect(screen.getByText('1 machine ignored (printers, crew PCs)')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Ignore' })[1])
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/cables/clients/ignored'
      && (c.body as { mac: string }).mac === '02:00:00:00:00:50')).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Patch to a seat' }))
    // The new cable starts with the port, and the seat whose IP the machine has.
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Switch port' })).toHaveValue('Gi1/0/30'))
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Seat' })).toHaveValue('A-9'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/cables'
      && (c.body as { seat: string }).seat === 'A-9')).toBe(true))
  })

  it('does not ask for MAC tables without the seat mapping', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/cables': data })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Cables />)
    expect(await screen.findByText('C-0001')).toBeInTheDocument()
    expect(api.calls.some((c) => c.path.startsWith('/api/cables/clients'))).toBe(false)
  })
})
