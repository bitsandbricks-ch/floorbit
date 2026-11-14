import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Incident, IncidentBoard, Job, JobsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Incidents from './Incidents'
import Jobs from './Jobs'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const me = { enabled: true, user: { username: 'ben', display_name: 'Ben', role: 'tech', permissions: ['incidents.work'] } }
const cells = ['B-5', 'B-6', 'B-7'].map((seat, i) => ({ seat, x: i * 32 - 48, y: -16, hit: seat === 'B-6', on: null }))
const job: Job = {
  id: 'j1', title: 'No internet at the seat', seat: 'B-6', switch_id: null, switch_name: null, circuit_id: null, circuit_name: null,
  status: 'assigned', team: 'access', source: 'helpdesk', reports: 1, created_at: now - 300, dispatched_at: now - 120, taken_at: null,
  notes: [], drawing: { shapes: [{ cx: 400, cy: 300, rotation: 0, w: 96, h: 32, name: 'B', cells }], box: '0 0 800 600', cell: 32 },
  target: [400, 300], from: [100, 300], hall: null,
}
const data: JobsData = { me: { on_duty: true, at: 'A-1', since: now - 3600 }, seats: ['A-1', 'B-5', 'B-6', 'B-7'], jobs: [job], can_dispatch: false }

describe('My jobs', () => {
  it('shows the job on the plan with a line from the tech, and answers it', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/jobs': data,
      'POST /api/jobs/j1/take': { id: 'j1', status: 'assigned', taken_at: now },
      'POST /api/jobs/j1/done': { id: 'j1', status: 'fixed', taken_at: now },
    })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<Jobs />)
    const card = await screen.findByRole('article', { name: 'No internet at the seat' })
    expect(within(card).getByRole('img', { name: 'Floor plan with the job at Seat B-6' })).toBeInTheDocument()
    expect(container.querySelector('.cell.hit')).not.toBeNull()
    expect(container.querySelector('line.route')).not.toBeNull()
    fireEvent.click(within(card).getByRole('button', { name: "On my way" }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/jobs/j1/take')).toBe(true))
    fireEvent.change(within(card).getByRole('textbox', { name: 'Note (optional)' }), { target: { value: 'Cable was loose' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/jobs/j1/done')?.body).toEqual({ note: 'Cable was loose' }))
    expect(await screen.findByText('Marked fixed.')).toBeInTheDocument()
  })

  it('goes off duty', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/jobs': { ...data, jobs: [] },
      'PUT /api/jobs/me': { on_duty: false, at: 'A-1', since: now },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Jobs />)
    expect(await screen.findByText('No jobs for you right now.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('switch', { name: /On duty/ }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ on_duty: false }))
  })
})

describe('Board dispatch', () => {
  it('sends an incident to the nearest tech and shows who is on duty', async () => {
    const incident: Incident = {
      id: 'i1', seat: 'B-6', switch_id: null, problem: null, team: 'access', assignee: null, source: 'board', reported_by: 'lea',
      reports: 1, notes: [], snapshot: null, created_at: now - 60, updated_at: now, title: 'Slow connection', status: 'open',
      can_work: true, can_assign: true,
    }
    const board: IncidentBoard = {
      incidents: [incident], teams: [{ id: 'access', name: 'Access', depth: 1 }], workable_teams: ['access'],
      assign_teams: ['access'], can_assign_any: true, problems: [],
    }
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['incidents.work', 'incidents.assign'] } },
      'GET /api/incidents': board, 'GET /api/incidents/people': {}, 'GET /api/switches': [],
      'GET /api/dispatch/crew': { crew: [{ username: 'ben', display_name: 'Ben', at: 'A-1', since: now, jobs: 0 }] },
      'POST /api/incidents/i1/dispatch': { id: 'i1', assignee: 'ben', display_name: 'Ben' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Incidents />)
    expect(await screen.findByText('Ben · A-1 · free')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Send to nearest tech' }))
    expect(await screen.findByText('Sent to Ben.')).toBeInTheDocument()
  })
})
