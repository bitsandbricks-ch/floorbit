import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import IncidentPage from './IncidentPage'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }
const board = { incidents: [{ id: 'i1', title: 'No internet at the seat', seat: 'A-7', switch_id: null, problem: null, team: null,
  status: 'open', assignee: null, source: 'helpdesk', reported_by: null, reports: 1, notes: [], snapshot: null,
  created_at: now - 60, updated_at: now, can_work: true, can_assign: false }],
teams: [], workable_teams: [], assign_teams: [], can_assign_any: false, problems: [] }

describe('the seat\'s link on its incident (issue #913)', () => {
  it('shows the link over the last hours, as on the floor plan', async () => {
    const seat = { seat: 'A-7', switch: 'sw-a-01', port: 'Gi1/0/7', state: 'offline',
      history: { from: now - 6 * 3600, to: now, start: true, changes: [[now - 600, 0]] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/incidents': board, 'GET /api/incidents/people': {},
      'GET /api/switches': [], 'GET /api/incidents/i1/history': { entries: [] }, 'GET /api/plan/seats/A-7': seat }).fn)
    renderWithApp(<Routes><Route path="/incidents/:id" element={<IncidentPage />} /></Routes>, '/incidents/i1')
    expect(await screen.findByRole('img', { name: /Offline since .*1 change in 6 h/ })).toBeInTheDocument()
  })
})
