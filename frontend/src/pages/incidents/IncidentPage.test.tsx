import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard } from '@/api/types'
import { OPTIONS } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import IncidentPage from './IncidentPage'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const base: Omit<Incident, 'id' | 'title' | 'status'> = {
  seat: 'A-1', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'sam',
  reports: 1, notes: [], snapshot: null, created_at: now - 300, updated_at: now,
  can_work: true, can_assign: false,
}
const board: IncidentBoard = {
  incidents: [
    { ...base, id: 'i1', title: 'No internet at the seat', status: 'open', source: 'helpdesk', reports: 2, reported_by: null,
      snapshot: { known: true, switch: 'sw-a-01', port: 'Gi1/0/3', link: 'down', mac_seen: false },
      speedtest: { down_mbps: 12.5, up_mbps: 9.1, ping_ms: 3.2, jitter_ms: 0.4, at: now - 120 },
      seat_note: { text: 'Cable swapped, watch it', by: 'ana', at: now - 600 },
      notes: [{ text: 'Checked the cable', by: 'sam', at: now - 60 }] },
    { ...base, id: 'i3', title: 'Cable swapped', status: 'fixed' },
  ],
  teams: [{ id: 'access', name: 'Access', depth: 1 }, { id: 'electrics', name: 'Electrics', depth: 0 }],
  workable_teams: ['access'],
  assign_teams: [],
  can_assign_any: false,
  problems: ['no-internet', 'slow', 'power', 'other'],
}
const tech = { enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions: ['incidents.work', 'ports.act'] } }
const routes = {
  ...OPTIONS,
  'GET /api/auth/me': tech,
  'GET /api/incidents': board,
  'GET /api/incidents/people': { access: [{ username: 'sam', display_name: 'Sam' }, { username: 'kim', display_name: 'Kim' }] },
  'GET /api/switches': [],
  'GET /api/ports': { available: true, needs_login: false, plugin: 'SSH' },
}
const open = (id: string) => renderWithApp(
  <Routes><Route path="/incidents/:id" element={<IncidentPage />} /></Routes>, `/incidents/${id}`)

describe('Incident page (#887)', () => {
  it('shows everything known about the incident and its notes', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    open('i1')
    expect((await screen.findAllByRole('heading', { name: 'No internet at the seat' })).length).toBeGreaterThan(0)
    expect(screen.getByText('From the seat')).toBeInTheDocument()
    expect(screen.getByText('2 reports')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 Gi1/0/3: link down, no device seen')).toBeInTheDocument()
    expect(screen.getByText('Speed test at the seat, 2 minutes ago: 12.5 down, 9.1 up Mbit/s, 3.2 ms')).toBeInTheDocument()
    expect(document.querySelector('[data-seat-note]')).toHaveTextContent('Crew note: Cable swapped, watch it ana · 10 minutes ago')
    expect(screen.getByText('Checked the cable')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /All incidents/ })).toHaveAttribute('href', '/incidents')
  })

  it('adds a note and takes the incident', async () => {
    const api = fakeFetch({ ...routes, 'PATCH /api/incidents/i1': { ...board.incidents[0] } })
    vi.stubGlobal('fetch', api.fn)
    open('i1')
    fireEvent.change(await screen.findByRole('textbox', { name: 'Add a note and press Enter' }), { target: { value: 'Swapped the patch cable' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add note' }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'PATCH', path: '/api/incidents/i1', body: { note: 'Swapped the patch cable' } }))
    fireEvent.click(screen.getByRole('button', { name: 'Take it' }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'PATCH', path: '/api/incidents/i1', body: { status: 'assigned', assignee: 'sam' } }))
  })

  it('bounces the seat\'s port and notes what it did', async () => {
    const api = fakeFetch({
      ...routes,
      'POST /api/ports/bounce': { ok: true, message: 'Gi1/0/3 on sw-a-01 bounced.' },
      'PATCH /api/incidents/i1': { ...board.incidents[0] },
    })
    vi.stubGlobal('fetch', api.fn)
    open('i1')
    fireEvent.click(await screen.findByRole('button', { name: 'Bounce port' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Bounce port' }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'POST', path: '/api/ports/bounce', body: { seat: 'A-1' } }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'PATCH', path: '/api/incidents/i1', body: { note: 'Gi1/0/3 on sw-a-01 bounced.' } }))
  })

  it('offers no bounce or note once fixed, only Reopen', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    open('i3')
    expect(await screen.findByRole('button', { name: 'Reopen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bounce port' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Take it' })).toBeNull()
  })

  it('says when a seat has had incidents before', async () => {
    const repeats: IncidentBoard = { ...board, incidents: [
      { ...base, id: 'r1', title: 'Third time', seat: 'B-7', status: 'open', created_at: now - 60 },
      { ...base, id: 'r2', title: 'Second time', seat: 'B-7', status: 'fixed', created_at: now - 3600 },
      { ...base, id: 'r3', title: 'First time', seat: 'B-7', status: 'fixed', created_at: now - 7200 },
    ] }
    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents': repeats }).fn)
    open('r1')
    expect(await screen.findByRole('link', { name: 'Incident no. 3 at this seat' })).toHaveAttribute('href', '/incidents?q=seat%3AB-7')
  })

  it('lets a lead pick who has it', async () => {
    const lead: IncidentBoard = { ...board, can_assign_any: true, assign_teams: ['access'],
      incidents: [{ ...board.incidents[0], can_assign: true }] }
    const api = fakeFetch({ ...routes, 'GET /api/incidents': lead, 'GET /api/dispatch/crew': { crew: [] },
      'PATCH /api/incidents/i1': { ...board.incidents[0] } })
    vi.stubGlobal('fetch', api.fn)
    open('i1')
    expect(await screen.findByRole('button', { name: 'Send to nearest tech' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Give to' })).toBeInTheDocument()
  })

  it('says when the incident is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    open('nope')
    expect(await screen.findByText('This incident is gone')).toBeInTheDocument()
  })
})
