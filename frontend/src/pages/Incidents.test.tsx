import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Incidents from './Incidents'

afterEach(() => vi.unstubAllGlobals())

const base: Omit<Incident, 'id' | 'title' | 'status'> = {
  seat: 'A-1', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'sam',
  reports: 1, notes: [], snapshot: null, created_at: Date.now() / 1000 - 300, updated_at: Date.now() / 1000,
  can_work: true, can_assign: false,
}
const board: IncidentBoard = {
  incidents: [
    { ...base, id: 'i1', title: 'No internet at the seat', status: 'open', source: 'helpdesk', reports: 2, reported_by: null,
      snapshot: { known: true, switch: 'sw-a-01', port: 'Gi1/0/3', link: 'down', mac_seen: false } },
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
  it('sorts incidents into columns with the seat report details', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />)
    const open = await screen.findByRole('region', { name: 'Open' })
    expect(within(open).getByText('No internet at the seat')).toBeInTheDocument()
    expect(within(open).getByText('From the seat')).toBeInTheDocument()
    expect(within(open).getByText('2 reports')).toBeInTheDocument()
    expect(within(open).getByText('sw-a-01 Gi1/0/3: link down, no device seen')).toBeInTheDocument()
    const worked = screen.getByRole('region', { name: 'Being worked' })
    expect(within(worked).getByText('With kim')).toBeInTheDocument()
    // Another team's incident: visible, but no buttons.
    expect(within(worked).queryByRole('button', { name: 'Fixed' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Seat QR codes' })).toBeNull()
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
})
