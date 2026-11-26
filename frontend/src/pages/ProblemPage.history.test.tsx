import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemDetail, TimelineEntry } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import IncidentPage from './incidents/IncidentPage'
import ProblemPage from './ProblemPage'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const history: TimelineEntry[] = [
  { t: now - 120, kind: 'alert', title: 'Log alert: Port flapping', target: 'sw-a-01 Gi1/0/9', severity: 'warn' },
  { t: now - 900, kind: 'outage', title: 'Switch went offline', target: 'sw-a-01', severity: 'down' },
]
const tech = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work', 'seats.view'] } }
const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['incidents.work', 'seats.view', 'audit.read'] } }
const detail: ProblemDetail = {
  problem: { id: 'attention:errors:x', kind: 'errors', level: 'warn', title: 'Errors rising on Gi1/0/9', where: 'sw-a-01 Gi1/0/9',
    since: now - 600, link: '/plan?switch=sw-a-01', switch_id: 's1', device: 'sw-a-01', incident: null },
  device: { id: 's1', name: 'sw-a-01' }, can_mute: true, can_report: true, may_see_people: false, history,
}

describe('what happened at the place (issues #882, #913)', () => {
  it('shows the problem\'s place history, linking to the changelog only for audit readers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/problems/attention%3Aerrors%3Ax': detail }).fn)
    const first = renderWithApp(<Routes><Route path="/problems/:id" element={<ProblemPage />} /></Routes>, '/problems/attention%3Aerrors%3Ax')
    const panel = await screen.findByTestId('place-history')
    expect(within(panel).getByText('Log alert: Port flapping')).toBeInTheDocument()
    expect(within(panel).getByText('Switch went offline')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open in the changelog' })).toBeNull()
    first.unmount()

    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/problems/attention%3Aerrors%3Ax': detail }).fn)
    renderWithApp(<Routes><Route path="/problems/:id" element={<ProblemPage />} /></Routes>, '/problems/attention%3Aerrors%3Ax')
    expect(await screen.findByRole('link', { name: 'Open in the changelog' })).toHaveAttribute('href', '/timeline?q=sw-a-01')
  })

  it('shows the incident\'s place history, or says there is none', async () => {
    const board = { incidents: [{ id: 'i1', title: 'Uplink flaps', seat: null, switch_id: 's1', switch_name: 'sw-a-01', problem: null, team: null,
      status: 'open', assignee: null, source: 'board', reported_by: 'kim', reports: 1, notes: [], snapshot: null,
      created_at: now - 60, updated_at: now, can_work: true, can_assign: false }],
    teams: [], workable_teams: [], assign_teams: [], can_assign_any: false, problems: [] }
    const routes = { 'GET /api/auth/me': tech, 'GET /api/incidents': board, 'GET /api/incidents/people': {}, 'GET /api/switches': [] }
    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents/i1/history': { entries: history } }).fn)
    const first = renderWithApp(<Routes><Route path="/incidents/:id" element={<IncidentPage />} /></Routes>, '/incidents/i1')
    expect(await within(await screen.findByTestId('place-history')).findByText('Switch went offline')).toBeInTheDocument()
    first.unmount()

    vi.stubGlobal('fetch', fakeFetch({ ...routes, 'GET /api/incidents/i1/history': { entries: [] } }).fn)
    renderWithApp(<Routes><Route path="/incidents/:id" element={<IncidentPage />} /></Routes>, '/incidents/i1')
    expect(await screen.findByText('No outages, incidents or alerts here in the last hours.')).toBeInTheDocument()
  })
})
