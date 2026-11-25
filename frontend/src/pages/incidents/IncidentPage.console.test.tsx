import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import IncidentPage from './IncidentPage'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const user = (permissions: string[]) => ({ enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions } })
const board = { incidents: [{ id: 'i1', title: 'No internet at the seat', seat: 'A-7', switch_id: null, problem: null, team: null,
  status: 'open', assignee: null, source: 'helpdesk', reported_by: null, reports: 1, notes: [], snapshot: null,
  created_at: now - 60, updated_at: now, can_work: false, can_assign: false }],
teams: [], workable_teams: [], assign_teams: [], can_assign_any: false, problems: [] }
const routes = { 'GET /api/incidents': board, 'GET /api/incidents/people': {}, 'GET /api/switches': [],
  'GET /api/incidents/i1/history': { entries: [] }, 'GET /api/features': { off: [] },
  'GET /api/plan/seats/A-7': { seat: 'A-7', switch: 'sw-a-01', port: 'Gi1/0/7', state: 'online' } }
const open = (permissions: string[]) => {
  vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/auth/me': user(permissions) }).fn)
  return renderWithApp(<Routes><Route path="/incidents/:id" element={<IncidentPage />} /></Routes>, '/incidents/i1')
}

describe('the switch console from an incident (issue #913)', () => {
  it('links to the console of the seat\'s switch for those who may open it', async () => {
    open(['incidents.work', 'terminal.open'])
    expect(await screen.findByRole('link', { name: 'Console of sw-a-01' })).toHaveAttribute('href', '/terminal?switch=sw-a-01')
  })

  it('offers no console without terminal.open', async () => {
    open(['incidents.work'])
    expect(await screen.findByText('What happened here')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Console of/ })).toBeNull()
  })
})
