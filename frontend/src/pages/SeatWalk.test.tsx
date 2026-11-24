import { cleanup, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatLocated, SeatWalkInfo } from '@/api/types'
import { OPTIONS, pick } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import SeatWalk from './SeatWalk'
import { leave } from './seatWalkLeave'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); sessionStorage.clear() })

const crew = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit', 'seats.view', 'seats.edit'] } }
const info: SeatWalkInfo = {
  agent_url: 'http://192.0.2.2:8908', switch_lookup: true, monitoring: true, keep_hours: 24,
  event: { id: 'main', name: '', status: 'live' },
}
const located = (seat: string, port: string, extra: Partial<SeatLocated> = {}): SeatLocated => ({
  ok: true, retry: false, seat, ip: '192.0.2.10', mac: '02:00:00:00:00:10', how: 'switch', ms: 1400, tries: 1,
  stale: false, found: { switch: 'sw-a-01', port }, steps: [{ step: 'switch', ok: true }], replaced: [], plan_seat: null, ...extra,
})
const WALKER = {
  'POST /api/seat-walk/walkers': () => ({ status: 201, body: { id: 'w1', who: 'Ana', rows: ['b1:1'], seat: null } }),
  'PUT /api/seat-walk/walkers/w1': { id: 'w1', who: 'Ana', rows: ['b1:1'], seat: 'A-1' },
  'DELETE /api/seat-walk/walkers/w1': { ok: true },
}
const notYet: SeatLocated = { ...located('A-2', ''), ok: false, retry: true, found: null, how: null, stale: true }

describe('SeatWalk', () => {
  it('with a typed MAC: watches for the cable seat after seat, waits out an old answer and offers to fix the plan', async () => {
    let tries = 0
    const api = fakeFetch({
      ...OPTIONS, ...WALKER, 'GET /api/auth/me': crew,
      'GET /api/seat-walk': info,
      'GET /api/seat-walk?rows=b1%3A1&order=rows': { ...info, rows: ['b1:1'], row_names: ['A 1'], seats: [{ seat: 'A-1', port: null }, { seat: 'A-2', port: null }] },
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
    await pick('Rows', 'A 1 (8 seats)')
    const macField = screen.getByRole('textbox', { name: /Laptop MAC/ })
    fireEvent.change(macField, { target: { value: 'nope' } })
    expect(await screen.findByText('That is not a MAC address.')).toBeInTheDocument()
    fireEvent.change(macField, { target: { value: '02-00-00-00-00-10' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))

    // No Locate to press: the page looks as soon as the seat is up, and moves on by itself.
    expect(await screen.findByRole('heading', { name: 'A-1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Locate' })).not.toBeInTheDocument()
    expect(await screen.findByText('A-1 is on sw-a-01 Gi1/0/1')).toBeInTheDocument()
    expect(screen.getByText('Read from the switch')).toBeInTheDocument()
    expect(screen.getByText('On to A-2 in a moment.')).toBeInTheDocument()

    expect(await screen.findByRole('heading', { name: 'A-2' }, { timeout: 4000 })).toBeInTheDocument()
    // The first answer still names A-1's port: the cable isn't in yet, the page waits and asks again.
    expect(await screen.findByText('Waiting for the laptop at A-2…')).toBeInTheDocument()
    expect(await screen.findByText('A-2 is on sw-a-01 Gi1/0/2', {}, { timeout: 6000 })).toBeInTheDocument()
    // Something to read: no moving on by itself.
    expect(screen.queryByText(/in a moment/)).not.toBeInTheDocument()
    expect(screen.getByText(/patch plan puts A-9 on sw-a-01 Gi1/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Put A-2 there in the patch plan' }))
    expect(await screen.findByText('Patch plan updated.')).toBeInTheDocument()

    const sent = api.calls.filter((c) => c.path === '/api/seat-walk/locate').map((c) => c.body)
    expect(sent[0]).toEqual({ seat: 'A-1', previous: null, mac: '02-00-00-00-00-10', mac_typed: true, run: expect.any(String) })
    // The next seat says where the last one was, so an old MAC table isn't taken for this seat.
    expect(sent[1]).toEqual({ seat: 'A-2', previous: { switch: 'sw-a-01', port: 'Gi1/0/1' }, mac: '02-00-00-00-00-10', mac_typed: true, run: expect.any(String) })
    expect(api.calls.some((c) => c.path === '/api/seat-walk/hello')).toBe(false)
    expect(sent).toHaveLength(3)
    // The walker said where they were, for the others' overview.
    expect(api.calls.filter((c) => c.path === '/api/seat-walk/walkers/w1' && c.method === 'PUT').map((c) => c.body))
      .toEqual(expect.arrayContaining([{ seat: 'A-1' }, { seat: 'A-2' }]))
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))
    expect(await screen.findByText('Done: 2 of 2 seats found')).toBeInTheDocument()
  }, 15_000)

  it('says why a seat failed', async () => {
    const api = fakeFetch({
      ...OPTIONS, ...WALKER, 'GET /api/auth/me': crew,
      'GET /api/seat-walk': info,
      'GET /api/seat-walk?rows=b1%3A1&order=rows': { ...info, rows: ['b1:1'], row_names: ['A 1'], seats: [{ seat: 'A-1', port: null }] },
      'POST /api/seat-walk/locate': () => ({ status: 409, body: { error: 'This laptop has 198.51.100.7, which is not in the seat networks.' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatWalk />)
    await pick('Rows', 'A 1 (8 seats)')
    fireEvent.change(screen.getByRole('textbox', { name: /Laptop MAC/ }), { target: { value: '02:00:00:00:00:10' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))
    expect(await screen.findByText('No port found for A-1')).toBeInTheDocument()
    expect(screen.getByText(/not in the seat networks/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('identifies the laptop through the local agent and carries on when it comes back', async () => {
    const routes = {
      ...OPTIONS, ...WALKER, 'GET /api/auth/me': crew,
      'GET /api/seat-walk': info,
      'GET /api/seat-walk?rows=b1%3A1&order=rows': { ...info, rows: ['b1:1'], row_names: ['A 1'], seats: [{ seat: 'A-1', port: null }, { seat: 'A-2', port: null }] },
      'POST /api/seat-walk/hello': { hello: 'code-for-a-1-xxxxxx', url: 'http://192.0.2.2:8908/floorbit/hello/code-for-a-1-xxxxxx' },
      'POST /api/seat-walk/locate': located('A-1', 'Gi1/0/1'),
    }
    let api = fakeFetch(routes)
    vi.stubGlobal('fetch', api.fn)
    const went = vi.spyOn(leave, 'to').mockImplementation(() => undefined)
    renderWithApp(<SeatWalk />)
    expect(await screen.findByText('http://192.0.2.2:8908')).toBeInTheDocument()
    await pick('Rows', 'A 1 (8 seats)')
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Locate' }))
    await vi.waitFor(() => expect(went).toHaveBeenCalled())
    const url = new URL(went.mock.calls[0][0])
    expect(url.origin + url.pathname).toBe('http://192.0.2.2:8908/floorbit/hello/code-for-a-1-xxxxxx')
    const back = new URL(url.searchParams.get('back')!)
    expect(back.origin).toBe(window.location.origin)
    expect(back.searchParams.get('hello')).toBe('code-for-a-1-xxxxxx')
    expect(api.calls.some((c) => c.path === '/api/seat-walk/locate')).toBe(false)

    // The agent sends the browser back with the code: the walk picks up at A-1 and locates.
    cleanup()
    window.history.replaceState(null, '', `${back.pathname}${back.search}`)
    api = fakeFetch(routes)
    vi.stubGlobal('fetch', api.fn)
    // The app may mount the page twice while it starts; the first mount takes the code off the address.
    renderWithApp(<SeatWalk />)
    cleanup()
    expect(window.location.search).toBe('')
    renderWithApp(<SeatWalk />)
    expect(await screen.findByText('A-1 is on sw-a-01 Gi1/0/1')).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.path === '/api/seat-walk/locate').map((c) => c.body)
    expect(sent[0]).toEqual({ seat: 'A-1', previous: null, hello: 'code-for-a-1-xxxxxx', run: expect.any(String) })
    expect(window.location.search).toBe('')
    expect(sessionStorage.length).toBe(0)
  })

  it('shows who walks which row, and takes a row over when asked', async () => {
    const hall = [
      { id: 'b1:1', name: '1', block_label: 'A', naming: 'block', seats: 8, found: 3, walker: { id: 'w9', who: 'Ben', seat: 'A-4' } },
      { id: 'b2:1', name: 'C', block_label: 'C\u2013D', naming: 'rows', seats: 12, found: 12, walker: null },
    ]
    let claims = 0
    const api = fakeFetch({
      ...OPTIONS, ...WALKER, 'GET /api/auth/me': crew,
      'GET /api/seat-walk': { ...info, hall },
      'GET /api/seat-walk?rows=b1%3A1&order=rows': { ...info, hall, rows: ['b1:1'], row_names: ['A 1'], seats: [{ seat: 'A-1', port: null }] },
      'POST /api/seat-walk/walkers': () => (++claims === 1
        ? { status: 409, body: { error: 'Someone else is walking one of these rows.', held: ['Ben'] } }
        : { status: 201, body: { id: 'w1', who: 'Ana', rows: ['b1:1'], seat: null } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatWalk />)
    expect(await screen.findByText('Block A, row 1')).toBeInTheDocument()
    expect(screen.getByText('Ben · A-4')).toBeInTheDocument()
    expect(screen.getByText('Row C')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('1 person walking')).toBeInTheDocument()
    await pick('Rows', 'A 1 (8 seats)')
    fireEvent.click(await screen.findByRole('button', { name: 'Start at A-1' }))
    expect(await screen.findByText('Ben is walking one of these rows.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Take them over' }))
    expect(await screen.findByRole('heading', { name: 'A-1' })).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.path === '/api/seat-walk/walkers').map((c) => c.body)
    expect(sent).toEqual([{ rows: ['b1:1'], take: false }, { rows: ['b1:1'], take: true }])
  })

  it('says when nobody knows where the agent is', async () => {
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': crew, 'GET /api/seat-walk': { ...info, agent_url: null },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SeatWalk />)
    expect(await screen.findByText(/No laptop in the hall has reached a local agent yet/)).toBeInTheDocument()
  })
})
