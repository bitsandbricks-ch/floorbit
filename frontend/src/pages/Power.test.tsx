import { fireEvent, screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Circuit, PowerOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Power from './Power'
import BoardPage from './power/BoardPage'
import CircuitPage from './power/CircuitPage'

// The list and the board and circuit pages, so a click from one lands on the other.
const app = (route = '/power') => renderWithApp(
  <Routes>
    <Route path="/power" element={<Power />} />
    <Route path="/power/boards/:id" element={<BoardPage />} />
    <Route path="/power/circuits/:id" element={<CircuitPage />} />
  </Routes>, route)

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const circuit = (over: Partial<Circuit> = {}): Circuit => ({
  id: 'c1', board: 'b1', name: 'A row 2', phase: 'L2', rating_a: 16, meter: '', switches: ['s1'],
  blocks: [{ block: 'blk', rows: [2] }], tripped: null,
  reading: { amps: 13.2, at: now - 120, source: 'manual', by: 'kim' }, state: 'warn', load_pct: 82.5,
  fed: { seats: ['A-4', 'A-5', 'A-6'], switches: [{ id: 's1', name: 'sw-a-01' }] }, feeds_label: 'A · row 2', feeds_parts: [{ block: 'A', rows: ['2'], by_rows: false }],
  ...over,
})
const overview = (over: Partial<PowerOverview> = {}): PowerOverview => ({
  enabled: true, boards: [{ id: 'b1', name: 'DB-1', location: 'West wall', x: 4, y: 40 }],
  circuits: [circuit(), circuit({ id: 'c2', name: 'Network rack', state: 'tripped', load_pct: null, reading: null,
    tripped: { by: 'kim', at: now - 60 }, feeds_label: '', feeds_parts: [], fed: { seats: [], switches: [{ id: 'core', name: 'core-01' }] } })],
  counts: { ok: 0, warn: 1, crit: 0, tripped: 1, unknown: 0 }, warn: 80, crit: 95, last_poll: null, plugins: 0,
  blocks: [{ id: 'blk', name: 'A', rows: 2, label: 'A', row_names: ['1', '2'] }], can_edit: false, can_read: true, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: ['floorplan.view'] } }

describe('Electrics', () => {
  it('shows each circuit with its load and what it feeds, each opening its own page', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/power': overview(), 'GET /api/switches': [] }).fn)
    app()
    const board = await screen.findByRole('region', { name: /DB-1/ })
    expect(within(board).getByRole('link', { name: 'DB-1' })).toHaveAttribute('href', '/power/boards/b1')
    const link = within(board).getByRole('link', { name: 'A row 2' })
    expect(link).toHaveAttribute('href', '/power/circuits/c1')
    const row = link.closest('tr') as HTMLElement
    expect(within(row).getByText('Getting close')).toBeInTheDocument()
    expect(within(row).getByText('13.2 A of 16 A (82.5 %)')).toBeInTheDocument()
    expect(within(row).getByText('A · row 2, sw-a-01')).toBeInTheDocument()
    expect(within(row).getByText('3 seats')).toBeInTheDocument()
    // No buttons on the rows: everything is done on the circuit's page (issue #877).
    expect(within(row).queryByRole('button')).toBeNull()
    expect(screen.getByText('1 tripped')).toBeInTheDocument()
    // One getting close and one tripped: a background tab shows two (issue #218).
    expect(document.title).toBe('(2) Electrics · Floorbit')
    // Someone on the Electrics team types readings in but can't change the circuits.
    expect(screen.queryByRole('link', { name: 'Add board' })).not.toBeInTheDocument()
  })

  it('keeps one action in the head and the rest behind More actions (#1044)', async () => {
    const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'plugins.run'] } }
    const fake = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/power': overview({ can_edit: true, plugins: 1 }), 'POST /api/power/check': overview({ can_edit: true, plugins: 1 }) })
    vi.stubGlobal('fetch', fake.fn)
    app()
    expect(await screen.findByRole('link', { name: 'Add circuit' })).toHaveAttribute('href', '/power/circuits/new')
    expect(screen.queryByRole('link', { name: 'Add board' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    expect(await screen.findByText('Add board')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Read the meters'))
    await vi.waitFor(() => expect(fake.calls.some((c) => c.method === 'POST' && c.path === '/api/power/check')).toBe(true))
  })

  it('sends a reading in watts and reports a trip on the circuit page', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/power': overview(), 'GET /api/switches': [],
      'POST /api/power/circuits/c1/reading': { circuit: circuit(), alerts: [] },
      'POST /api/power/circuits/c1/trip': { circuit: circuit(), alerts: [] },
    })
    vi.stubGlobal('fetch', fake.fn)
    app('/power/circuits/c1')
    fireEvent.click(await screen.findByText('Watts'))
    fireEvent.change(screen.getByLabelText(/Load/), { target: { value: '2900' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path.endsWith('/reading'))?.body).toEqual({ watts: 2900 }))
    fireEvent.click(screen.getByRole('button', { name: 'Mark as tripped' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path.endsWith('/trip'))?.body).toEqual({ tripped: true }))
    // Without floor plan rights there is no form to change the circuit.
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
  })

  it('asks in its own dialog before it removes a circuit, then goes back to its board', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/power': overview({ can_edit: true }), 'GET /api/switches': [],
      'DELETE /api/power/circuits/c1': { ok: true },
    })
    vi.stubGlobal('fetch', fake.fn)
    app('/power/circuits/c1')
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Remove A row 2?')).toBeInTheDocument()
    expect(fake.calls.some((c) => c.method === 'DELETE')).toBe(false)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Yes, go ahead' }))
    await vi.waitFor(() => expect(fake.calls.some((c) => c.method === 'DELETE' && c.path === '/api/power/circuits/c1')).toBe(true))
    expect(await screen.findByRole('link', { name: 'Add circuit' })).toHaveAttribute('href', '/power/circuits/new?board=b1')
  })

  it('changes a board on its page and lists its circuits', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/power': overview({ can_edit: true }), 'GET /api/switches': [],
      'PATCH /api/power/boards/b1': { id: 'b1', name: 'DB-2', location: 'West wall', x: 4, y: 40 },
    })
    vi.stubGlobal('fetch', fake.fn)
    app('/power/boards/b1')
    expect(await screen.findByRole('link', { name: 'Network rack' })).toHaveAttribute('href', '/power/circuits/c2')
    // A board with circuits can't be removed.
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'DB-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({ name: 'DB-2', location: 'West wall' }))
  })

  it('says so when a circuit is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/power': overview(), 'GET /api/switches': [] }).fn)
    app('/power/circuits/nope')
    expect(await screen.findByText('This circuit is gone.')).toBeInTheDocument()
  })

  it('says so when the layer is off', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/power': overview({ enabled: false }), 'GET /api/switches': [] }).fn)
    app()
    expect(await screen.findByText(/The power layer is off/)).toBeInTheDocument()
  })
})
