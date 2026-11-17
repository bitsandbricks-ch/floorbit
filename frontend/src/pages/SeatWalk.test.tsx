import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatLocated, SeatWalkInfo } from '@/api/types'
import { OPTIONS } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import SeatWalk from './SeatWalk'

afterEach(() => vi.unstubAllGlobals())

const crew = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit', 'seats.view', 'seats.edit'] } }
const info: SeatWalkInfo = {
  ip: '192.0.2.10', ip_allowed: true, switch_lookup: true, monitoring: true, keep_hours: 24,
  event: { id: 'main', name: '', status: 'live' },
}
const located = (seat: string, port: string, extra: Partial<SeatLocated> = {}): SeatLocated => ({
  ok: true, retry: false, seat, ip: '192.0.2.10', mac: '02:00:00:00:00:10', how: 'switch', ms: 1400, tries: 1,
  stale: false, found: { switch: 'sw-a-01', port }, steps: [{ step: 'switch', ok: true }], replaced: [], plan_seat: null, ...extra,
})
const notYet: SeatLocated = { ...located('A-2', ''), ok: false, retry: true, found: null, how: null, stale: true }

describe('SeatWalk', () => {
  it('locates seat after seat, shows the port, waits out an old answer and offers to fix the plan', async () => {
    let tries = 0
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': crew,
      'GET /api/seat-blocks': [{ id: 'b1', name: 'A', cols: 2, rows: 1, hall_id: 'h' }],
      'GET /api/seat-walk': info,
      'GET /api/seat-walk?block=b1&order=rows': { ...info, block: 'A', seats: [{ seat: 'A-1', port: null }, { seat: 'A-2', port: null }] },
      'POST /api/seat-walk/locate': () => {
        tries += 1
        if (tries === 1) return { body: located('A-1', 'Gi1/0/1') }
        if (tries === 2) return { body: notYet }
        return { body: located('A-2', 'Gi1/0/2', { how: 'monitoring', plan_seat: 'A-9' }) }
      },
      'POST /api/cables/assign': { cable: {}, changed: ['C-0001'], other_seat: 'A-9' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatWalk />)
    expect(await screen.findByText(/cleared 24 hours after it ends/)).toBeInTheDocument()
    expect(screen.getByText(/need portfast/)).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('combobox', { name: 'Seat block' }))
    fireEvent.click(await screen.findByRole('option', { name: 'A (2)', hidden: true }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))

    expect(await screen.findByRole('heading', { name: 'A-1' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Locate' }))
    expect(await screen.findByText('A-1 is on sw-a-01 Gi1/0/1')).toBeInTheDocument()
    expect(screen.getByText('Read from the switch')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next seat: A-2' }))

    expect(await screen.findByRole('heading', { name: 'A-2' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Locate' }))
    // The first answer still names A-1's port: the page asks again by itself.
    expect(await screen.findByText('A-2 is on sw-a-01 Gi1/0/2')).toBeInTheDocument()
    expect(screen.getByText(/patch plan puts A-9 on sw-a-01 Gi1/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Put A-2 there in the patch plan' }))
    expect(await screen.findByText('Patch plan updated.')).toBeInTheDocument()

    const sent = api.calls.filter((c) => c.path === '/api/seat-walk/locate').map((c) => c.body)
    expect(sent[0]).toEqual({ seat: 'A-1', previous: null })
    // The next seat says where the last one was, so an old MAC table isn't taken for this seat.
    expect(sent[1]).toEqual({ seat: 'A-2', previous: { switch: 'sw-a-01', port: 'Gi1/0/1' }, mac: '02:00:00:00:00:10', mac_ip: '192.0.2.10' })
    expect(sent).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    expect(await screen.findByText('Done: 2 of 2 seats found')).toBeInTheDocument()
  })

  it('says why a seat failed', async () => {
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': crew,
      'GET /api/seat-blocks': [{ id: 'b1', name: 'A', cols: 1, rows: 1, hall_id: 'h' }],
      'GET /api/seat-walk': info,
      'GET /api/seat-walk?block=b1&order=rows': { ...info, block: 'A', seats: [{ seat: 'A-1', port: null }] },
      'POST /api/seat-walk/locate': () => ({ status: 409, body: { error: 'This laptop has 198.51.100.7, which is not in the seat networks.' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatWalk />)
    fireEvent.click(await screen.findByRole('combobox', { name: 'Seat block' }))
    fireEvent.click(await screen.findByRole('option', { name: 'A (1)', hidden: true }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Locate' }))
    expect(await screen.findByText('No port found for A-1')).toBeInTheDocument()
    expect(screen.getByText(/not in the seat networks/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
