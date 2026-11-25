import { fireEvent, screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemDetail } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import ProblemPage from './ProblemPage'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work', 'seats.view'] } }
const detail = (over: Partial<ProblemDetail['problem']> = {}): ProblemDetail => ({
  problem: { id: 'attention:errors:s1:Gi1/0/9', kind: 'errors', level: 'warn', title: 'Errors rising on Gi1/0/9', where: 'sw-a-01 Gi1/0/9 (seat A-9)',
    since: now - 600, link: '/plan?switch=sw-a-01', switch_id: 's1', seat: 'A-9', device: 'sw-a-01', incident: null, ...over },
  device: { id: 's1', name: 'sw-a-01' }, can_mute: true, can_report: true, may_see_people: true,
})
const path = '/api/problems/attention%3Aerrors%3As1%3AGi1%2F0%2F9'
const open = (routes: Record<string, unknown>) => {
  const api = fakeFetch({ 'GET /api/auth/me': me, ...routes })
  vi.stubGlobal('fetch', api.fn)
  renderWithApp(<Routes><Route path="/problems/:id" element={<ProblemPage />} /></Routes>,
    `/problems/${encodeURIComponent('attention:errors:s1:Gi1/0/9')}`)
  return api
}

describe('a problem page (issue #882)', () => {
  it('says what and where, and links where to look next', async () => {
    open({ [`GET ${path}`]: detail() })
    expect((await screen.findAllByRole('heading', { name: 'Errors rising on Gi1/0/9' })).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'sw-a-01 in the inventory' })).toHaveAttribute('href', '/inventory/devices/s1')
    expect(screen.getByRole('link', { name: 'Seat A-9 on the floor plan' })).toHaveAttribute('href', '/plan?seat=A-9')
    expect(screen.getByRole('link', { name: 'Its logs' })).toHaveAttribute('href', '/logs?seat=A-9')
    expect(screen.getByRole('link', { name: 'Machines seen at the seat' })).toHaveAttribute('href', '/endpoints?seat=A-9')
  })

  it('shows the seat\'s newest log lines', async () => {
    const line = { id: 7, ts: now - 30, facility: 23, severity: 'err', host: null, program: '%LINK-3-UPDOWN',
      message: 'Interface Gi1/0/9, changed state to down', sender: '192.0.2.9', device: 'sw-a-01', port: 'gi1/0/9', seat: 'A-9' }
    const api = open({ [`GET ${path}`]: detail(), 'GET /api/logs?seat=A-9&limit=20': { lines: [line], status: {} } })
    expect(await screen.findByText('Interface Gi1/0/9, changed state to down')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in Logs' })).toHaveAttribute('href', '/logs?seat=A-9')
    expect(api.calls.some((c) => c.path === '/api/logs?seat=A-9&limit=20')).toBe(true)
  })

  it('shows no logs to those who may not see people', async () => {
    const api = open({ [`GET ${path}`]: { ...detail(), may_see_people: false } })
    expect((await screen.findAllByRole('heading', { name: 'Errors rising on Gi1/0/9' })).length).toBeGreaterThan(0)
    expect(screen.queryByText('Recent logs')).not.toBeInTheDocument()
    expect(api.calls.some((c) => c.path.startsWith('/api/logs'))).toBe(false)
  })

  it('makes an incident for the seat, linked back to the problem', async () => {
    const api = open({ [`GET ${path}`]: detail(), 'POST /api/incidents': { status: 201, body: {} } })
    fireEvent.click(await screen.findByRole('button', { name: 'Make an incident' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body)
      .toEqual({ seat: 'A-9', title: 'Errors rising on Gi1/0/9', from_problem: 'attention:errors:s1:Gi1/0/9' }))
  })

  it('links its open incident instead', async () => {
    open({ [`GET ${path}`]: detail({ incident: 'abc123' }) })
    expect(await screen.findByRole('link', { name: 'Incident open' })).toHaveAttribute('href', '/incidents/abc123')
    expect(screen.queryByRole('button', { name: 'Make an incident' })).not.toBeInTheDocument()
  })

  it('says when the problem is over', async () => {
    open({ [`GET ${path}`]: () => ({ status: 404, body: { error: 'This problem is over.' } }) })
    expect(await screen.findByText('This problem is over')).toBeInTheDocument()
  })
})
