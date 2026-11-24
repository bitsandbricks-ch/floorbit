import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard } from '@/api/types'
import { OPTIONS } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import Incidents from '../Incidents'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const base: Omit<Incident, 'id' | 'title' | 'status'> = {
  seat: 'A-1', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'sam',
  reports: 1, notes: [], snapshot: null, created_at: now - 300, updated_at: now, can_work: true, can_assign: false,
}
const board: IncidentBoard = {
  incidents: [
    { ...base, id: 'i3', title: 'Cable swapped', status: 'fixed', seat: 'C-3' },
    { ...base, id: 'i2', title: 'No power', status: 'assigned', team: 'electrics', assignee: 'kim', seat: 'B-2' },
    { ...base, id: 'i1', title: 'No internet at the seat', status: 'open' },
  ],
  teams: [{ id: 'access', name: 'Access', depth: 1 }, { id: 'electrics', name: 'Electrics', depth: 0 }],
  workable_teams: ['access'], assign_teams: [], can_assign_any: false,
  problems: ['no-internet', 'slow', 'power', 'other'],
}
const routes = {
  ...OPTIONS,
  'GET /api/auth/me': { enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions: ['incidents.work'] } },
  'GET /api/incidents': board,
  'GET /api/incidents/people': { access: [{ username: 'sam', display_name: 'Sam' }] },
  'GET /api/switches': [],
}

describe('Incidents as a table (issue #887)', () => {
  it('lists every incident in one table, open ones first, each linking to its page', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents?view=table')
    const table = await screen.findByRole('table', { name: 'Incidents' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('link').textContent)).toEqual(['No internet at the seat', 'No power', 'Cable swapped'])
    expect(within(rows[1]).getByText('kim')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Electrics')).toBeInTheDocument()
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', '/incidents/i1')
    expect(screen.getByText('3 incidents')).toBeInTheDocument()
  })

  it('switches between board and table', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents')
    expect(await screen.findByRole('region', { name: 'Open' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: 'Table' }))
    expect(await screen.findByRole('table', { name: 'Incidents' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Open' })).toBeNull()
  })

  it('keeps the filter in the table', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Incidents />, '/incidents?view=table&q=power')
    const table = await screen.findByRole('table', { name: 'Incidents' })
    expect(within(table).getAllByRole('row')).toHaveLength(2)
    expect(within(table).getByText('No power')).toBeInTheDocument()
  })
})
