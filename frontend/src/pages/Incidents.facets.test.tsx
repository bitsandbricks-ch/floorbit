import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard } from '@/api/types'
import { OPTIONS } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import Incidents from './Incidents'
import { matchesFacets } from './incidents/filter'

afterEach(() => vi.unstubAllGlobals())

const base: Omit<Incident, 'id' | 'title' | 'status'> = {
  seat: 'A-1', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'sam',
  reports: 1, notes: [], snapshot: null, created_at: Date.now() / 1000 - 300, updated_at: Date.now() / 1000,
  can_work: true, can_assign: false,
}
const board: IncidentBoard = {
  incidents: [
    { ...base, id: 'i1', title: 'Seat is offline', status: 'open' },
    { ...base, id: 'i2', title: 'Breaker tripped', status: 'assigned', seat: null, circuit_id: 'c1', circuit_name: 'Row B',
      team: 'electrics', assignee: 'kim', can_work: false },
    { ...base, id: 'i3', title: 'Uplink flapping', status: 'assigned', seat: null, switch_id: 's1', switch_name: 'sw-a-01', assignee: 'sam' },
  ],
  teams: [{ id: 'access', name: 'Access', depth: 1 }, { id: 'electrics', name: 'Electrics', depth: 0 }],
  workable_teams: ['access'], assign_teams: [], can_assign_any: false, problems: [],
}
const routes = {
  ...OPTIONS,
  'GET /api/auth/me': { enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions: ['incidents.work'] } },
  'GET /api/incidents': board,
  'GET /api/incidents/people': {},
  'GET /api/switches': [],
}

async function pick(button: RegExp, item: RegExp) {
  fireEvent.click(screen.getByRole('button', { name: button }))
  fireEvent.click(await screen.findByRole('menuitem', { name: item, hidden: true }))
}

describe('the board\'s filter menus (issue #887)', () => {
  it('narrows the board to one team', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />)
    const worked = await screen.findByRole('region', { name: 'Being worked' })
    expect(within(worked).getByText('Breaker tripped')).toBeInTheDocument()
    await pick(/^Team: Any team/, /^Electrics/)
    await waitFor(() => expect(within(worked).queryByText('Uplink flapping')).toBeNull())
    expect(within(screen.getByRole('region', { name: 'Open' })).getByText('Nothing matches the filter.')).toBeInTheDocument()
    expect(within(worked).getByText('Breaker tripped')).toBeInTheDocument()
    expect(within(worked).queryByText('Uplink flapping')).toBeNull()
  })

  it('opens the table filtered by state and place from the address', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents?view=table&state=assigned&where=switch')
    expect(await screen.findByText('Uplink flapping')).toBeInTheDocument()
    expect(screen.queryByText('Seat is offline')).toBeNull()
    expect(screen.queryByText('Breaker tripped')).toBeNull()
    expect(screen.getByRole('button', { name: /^State: Being worked/ })).toBeInTheDocument()
  })

  it('keeps "Assigned to me", "What I can work", team, state and place apart', () => {
    const [seat, power, uplink] = board.incidents
    const all = { mine: '', team: '', state: 'all', where: 'all' }
    expect(board.incidents.filter((i) => matchesFacets(i, { ...all, mine: '1' }, 'sam'))).toEqual([uplink])
    expect(board.incidents.filter((i) => matchesFacets(i, { ...all, mine: 'can' }, 'sam'))).toEqual([seat, uplink])
    expect(board.incidents.filter((i) => matchesFacets(i, { ...all, team: 'electrics' }, 'sam'))).toEqual([power])
    expect(board.incidents.filter((i) => matchesFacets(i, { ...all, state: 'open' }, 'sam'))).toEqual([seat])
    expect(board.incidents.filter((i) => matchesFacets(i, { ...all, where: 'circuit' }, 'sam'))).toEqual([power])
    expect(matchesFacets(uplink, { ...all, mine: '1' }, undefined)).toBe(false)
  })
})
