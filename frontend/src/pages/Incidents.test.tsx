import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Incidents from './Incidents'
import { matchesFilter } from './incidents/filter'

afterEach(() => vi.unstubAllGlobals())

const base: Omit<Incident, 'id' | 'title' | 'status'> = {
  seat: 'A-1', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'sam',
  reports: 1, notes: [], snapshot: null, created_at: Date.now() / 1000 - 300, updated_at: Date.now() / 1000,
  can_work: true, can_assign: false,
}
const board: IncidentBoard = {
  incidents: [
    { ...base, id: 'i1', title: 'No internet at the seat', status: 'open', source: 'helpdesk', reports: 2, reported_by: null,
      snapshot: { known: true, switch: 'sw-a-01', port: 'Gi1/0/3', link: 'down', mac_seen: false },
      speedtest: { down_mbps: 12.5, up_mbps: 9.1, ping_ms: 3.2, jitter_ms: 0.4, at: Date.now() / 1000 - 120 },
      seat_note: { text: 'Cable swapped, watch it', by: 'ana', at: Date.now() / 1000 - 600 } },
    { ...base, id: 'i2', title: 'No power', status: 'assigned', team: 'electrics', assignee: 'kim', can_work: false },
    { ...base, id: 'i3', title: 'Cable swapped', status: 'fixed' },
  ],
  teams: [{ id: 'access', name: 'Access', depth: 1 }, { id: 'electrics', name: 'Electrics', depth: 0 }],
  workable_teams: ['access'],
  assign_teams: [],
  can_assign_any: false,
  problems: ['no-internet', 'slow', 'power', 'other'],
}
const routes = {
  'GET /api/auth/me': { enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions: ['incidents.work'] } },
  'GET /api/incidents': board,
  'GET /api/incidents/people': { access: [{ username: 'sam', display_name: 'Sam' }] },
  'GET /api/switches': [],
}

describe('Incident board', () => {
  it('says when an open incident has waited 10 minutes with nobody on it', async () => {
    const now = Date.now() / 1000
    const waiting: IncidentBoard = { ...board, incidents: [
      { ...base, id: 'w1', title: 'Waiting long', status: 'open', created_at: now - 25 * 60 },
      { ...base, id: 'w2', title: 'Just in', status: 'open', created_at: now - 5 * 60 },
      { ...base, id: 'w3', title: 'Old but taken', status: 'assigned', assignee: 'sam', created_at: now - 40 * 60 },
      { ...base, id: 'w4', title: 'Overnight', status: 'open', created_at: now - (13 * 60 + 38) * 60 },
    ] }
    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents': waiting }).fn)
    renderWithApp(<Incidents />)
    const long = (await screen.findByText('Waiting long')).closest('[data-incident]') as HTMLElement
    expect(within(long).getByText('Waiting 25 min')).toBeInTheDocument()
    const fresh = screen.getByText('Just in').closest('[data-incident]') as HTMLElement
    expect(within(fresh).queryByText(/^Waiting/)).toBeNull()
    const taken = screen.getByText('Old but taken').closest('[data-incident]') as HTMLElement
    expect(within(taken).queryByText(/^Waiting/)).toBeNull()
    const night = screen.getByText('Overnight').closest('[data-incident]') as HTMLElement
    expect(within(night).getByText('Waiting 13 h 38 min')).toBeInTheDocument()
  })

  it('puts waiting incidents on top of the open column, longest first', async () => {
    const now = Date.now() / 1000
    const queue: IncidentBoard = { ...board, incidents: [
      { ...base, id: 'q1', title: 'Newest', status: 'open', created_at: now - 60 },
      { ...base, id: 'q2', title: 'Waiting a bit', status: 'open', created_at: now - 15 * 60 },
      { ...base, id: 'q3', title: 'Recent', status: 'open', created_at: now - 4 * 60 },
      { ...base, id: 'q4', title: 'Waiting longest', status: 'open', created_at: now - 50 * 60 },
    ] }
    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents': queue }).fn)
    renderWithApp(<Incidents />)
    const open = await screen.findByRole('region', { name: 'Open' })
    await within(open).findByText('Newest')
    const titles = Array.from(open.querySelectorAll('[data-incident]')).map((el) => el.textContent ?? '')
    const order = ['Waiting longest', 'Waiting a bit', 'Newest', 'Recent'].map((x) => titles.findIndex((tt) => tt.includes(x)))
    expect(order).toEqual([0, 1, 2, 3])
  })

  it('sorts incidents into columns with the seat report details', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />)
    const open = await screen.findByRole('region', { name: 'Open' })
    expect(within(open).getByText('No internet at the seat')).toBeInTheDocument()
    expect(document.title).toBe('(1) Incidents · Floorbit')
    expect(within(open).getByText('From the seat')).toBeInTheDocument()
    expect(within(open).getByText('2 reports')).toBeInTheDocument()
    expect(within(open).getByText('sw-a-01 Gi1/0/3: link down, no device seen')).toBeInTheDocument()
    expect(within(open).getByText('Speed test at the seat, 2 min ago: 12.5 down, 9.1 up Mbit/s, 3.2 ms')).toBeInTheDocument()
    expect(within(open).getAllByRole('link', { name: 'Seat A-1' })[0]).toHaveAttribute('href', '/plan?seat=A-1')
    expect(open.querySelector('[data-seat-note]')).toHaveTextContent('Crew note: Cable swapped, watch it ana · 10 min ago')
    expect(screen.getByRole('region', { name: 'Being worked' }).querySelector('[data-seat-note]')).toBeNull()
    const worked = screen.getByRole('region', { name: 'Being worked' })
    expect(within(worked).getByText('With kim')).toBeInTheDocument()
    // Another team's incident: visible, but no buttons.
    expect(within(worked).queryByRole('button', { name: 'Fixed' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Seat QR codes' })).toBeNull()
  })

  it('filters the board from the address', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents?q=KIM')
    const worked = await screen.findByRole('region', { name: 'Being worked' })
    expect(within(worked).getByText('No power')).toBeInTheDocument()
    const open = screen.getByRole('region', { name: 'Open' })
    expect(within(open).getByText('Nothing matches the filter.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Filter incidents' })).toHaveValue('KIM')
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter incidents' }), { target: { value: 'internet' } })
    expect(await within(open).findByText('No internet at the seat')).toBeInTheDocument()
    expect(within(worked).queryByText('No power')).toBeNull()
  })

  it('puts the cursor in the filter on /, with or without Shift (issue #226)', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents?q=KIM')
    const box = await screen.findByRole('textbox', { name: 'Filter incidents' })
    expect(box).toHaveAttribute('aria-keyshortcuts', '/')
    fireEvent.keyDown(document.documentElement, { key: '/', code: 'Slash' })
    expect(box).toHaveFocus()
    expect([(box as HTMLInputElement).selectionStart, (box as HTMLInputElement).selectionEnd]).toEqual([0, 3])
    box.blur()
    fireEvent.keyDown(document.documentElement, { key: '/', code: 'Digit7', shiftKey: true })
    expect(box).toHaveFocus()
  })

  it('matches title, place, people, team and notes', () => {
    const i = { ...board.incidents[1], notes: [{ by: 'kim', at: 1, text: 'Breaker 3 tripped' }] }
    expect(matchesFilter(i, '')).toBe(true)
    expect(matchesFilter(i, 'power')).toBe(true)
    expect(matchesFilter(i, 'breaker')).toBe(true)
    expect(matchesFilter(i, 'Electrics', { electrics: 'Electrics' })).toBe(true)
    expect(matchesFilter(i, 'switch')).toBe(false)
  })

  it('takes an incident', async () => {
    const api = fakeFetch({ ...routes, 'PATCH /api/incidents/i1': { ...board.incidents[0], status: 'assigned', assignee: 'sam' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Incidents />)
    const open = await screen.findByRole('region', { name: 'Open' })
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/auth/me')).toBe(true))
    fireEvent.click(within(open).getByRole('button', { name: 'Take it' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ status: 'assigned', assignee: 'sam' }))
  })
  it('takes the oldest open incident this account can work', async () => {
    const now = Date.now() / 1000
    const queue: IncidentBoard = { ...board, incidents: [
      { ...base, id: 'n1', title: 'Newer', status: 'open', created_at: now - 120 },
      { ...base, id: 'n2', title: 'Oldest but not mine', status: 'open', created_at: now - 3600, can_work: false },
      { ...base, id: 'n3', title: 'Oldest I can work', status: 'open', created_at: now - 1800 },
      { ...base, id: 'n4', title: 'Taken', status: 'assigned', assignee: 'kim', created_at: now - 7200 },
    ] }
    const api = fakeFetch({ ...routes, 'GET /api/incidents': queue,
      'PATCH /api/incidents/n3': { ...queue.incidents[2], status: 'assigned', assignee: 'sam' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Incidents />)
    const take = await screen.findByRole('button', { name: 'Take the next one' })
    await waitFor(() => expect(take).toBeEnabled())
    fireEvent.click(take)
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.path).toBe('/api/incidents/n3'))
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ status: 'assigned', assignee: 'sam' })
    expect(await screen.findByText('You have it: Oldest I can work')).toBeInTheDocument()
  })

  it('has nothing to take when nothing open is workable', async () => {
    const none: IncidentBoard = { ...board, incidents: [board.incidents[1], board.incidents[2]] }
    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents': none }).fn)
    renderWithApp(<Incidents />)
    const take = await screen.findByRole('button', { name: 'Take the next one' })
    expect(take).toBeDisabled()
    expect(take).toHaveAttribute('title', 'Nothing open that you can work')
  })
})
