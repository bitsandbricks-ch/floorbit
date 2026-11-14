import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Circuit, PowerOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Power from './Power'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const circuit = (over: Partial<Circuit> = {}): Circuit => ({
  id: 'c1', board: 'b1', name: 'A row 2', phase: 'L2', rating_a: 16, meter: '', switches: ['s1'],
  blocks: [{ block: 'blk', rows: [2] }], tripped: null,
  reading: { amps: 13.2, at: now - 120, source: 'manual', by: 'kim' }, state: 'warn', load_pct: 82.5,
  fed: { seats: ['A-4', 'A-5', 'A-6'], switches: [{ id: 's1', name: 'sw-a-01' }] }, feeds_label: 'block A row 2',
  ...over,
})
const overview = (over: Partial<PowerOverview> = {}): PowerOverview => ({
  enabled: true, boards: [{ id: 'b1', name: 'DB-1', location: 'West wall', x: 4, y: 40 }],
  circuits: [circuit(), circuit({ id: 'c2', name: 'Network rack', state: 'tripped', load_pct: null, reading: null,
    tripped: { by: 'kim', at: now - 60 }, feeds_label: '', fed: { seats: [], switches: [{ id: 'core', name: 'core-01' }] } })],
  counts: { ok: 0, warn: 1, crit: 0, tripped: 1, unknown: 0 }, warn: 80, crit: 95, last_poll: null, plugins: 0,
  blocks: [{ id: 'blk', name: 'A', rows: 2 }], can_edit: false, can_read: true, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: ['floorplan.view'] } }

describe('Electrics', () => {
  it('shows each circuit with its load and what it feeds', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/power': overview(), 'GET /api/switches': [] }).fn)
    renderWithApp(<Power />)
    const board = await screen.findByRole('region', { name: /DB-1/ })
    const row = within(board).getByText('A row 2').closest('tr') as HTMLElement
    expect(within(row).getByText('Getting close')).toBeInTheDocument()
    expect(within(row).getByText('13.2 A of 16 A (82.5 %)')).toBeInTheDocument()
    expect(within(row).getByText('block A row 2, sw-a-01')).toBeInTheDocument()
    expect(within(row).getByText('3 seats')).toBeInTheDocument()
    expect(screen.getByText('1 tripped')).toBeInTheDocument()
    // Someone on the Electrics team types readings in but can't change the circuits.
    expect(screen.queryByRole('button', { name: 'Add board' })).not.toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('sends a reading in watts and reports a trip', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/power': overview(), 'GET /api/switches': [],
      'POST /api/power/circuits/c1/reading': { circuit: circuit(), alerts: [] },
      'POST /api/power/circuits/c1/trip': { circuit: circuit(), alerts: [] },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Power />)
    const row = (await screen.findByText('A row 2')).closest('tr') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'Reading' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByText('Watts'))
    fireEvent.change(within(dialog).getByLabelText(/Load/), { target: { value: '2900' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path.endsWith('/reading'))?.body).toEqual({ watts: 2900 }))
    fireEvent.click(within(row).getByRole('button', { name: 'Tripped' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path.endsWith('/trip'))?.body).toEqual({ tripped: true }))
  })

  it('says so when the layer is off', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/power': overview({ enabled: false }), 'GET /api/switches': [] }).fn)
    renderWithApp(<Power />)
    expect(await screen.findByText(/The power layer is off/)).toBeInTheDocument()
  })
})
