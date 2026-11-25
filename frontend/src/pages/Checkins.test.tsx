import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CheckinOverview, CrewCheckin } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Checkins from './Checkins'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: false }
const now = Date.now() / 1000
const row = (seat: string, extra: Partial<CrewCheckin> = {}): CrewCheckin => ({
  seat, username: 'pixel', ip: '192.0.2.22', mac: null, device: 'pc', wired: 'pending', port: null, learned: null,
  pin: true, checked_in_at: now - 30, verified_at: null, ...extra,
})
const data: CheckinOverview = {
  counts: { checked_in: 3, pending: 1, verified: 1, not_wired: 1, unverified: 0, conflicts: 1, learned: 1, unused_pins: 21, pins: 24 },
  rows: [
    row('A-2', { wired: 'verified', port: { switch: 'sw-a-01', port: 'Gi1/0/2' }, learned: { switch: 'sw-a-01', port: 'Gi1/0/2', learned_at: now } }),
    row('A-3', { username: 'nova', ip: '192.0.2.24' }),
    row('A-4', { username: 'orbit', ip: '192.0.2.30', device: 'mobile', wired: 'not_wired', pin: false }),
  ],
  conflicts: [{ kind: 'plan', seat: 'A-2', other: ['A-7'], switch: 'sw-a-01', port: 'Gi1/0/2' }],
  portal: { fetches: [{ at: now - 5, agent: 'hall-a', done: 3 }], public_url: 'https://floor.example.com' },
  verifier: { last_error: null },
}

describe('Checkins', () => {
  it('says check-in is off and links admins to its settings instead of an error', async () => {
    const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/checkins/overview': () => ({ status: 404, body: { error: 'Check-in is disabled' } }),
    }).fn)
    renderWithApp(<Checkins />, '/checkins')
    expect(await screen.findByText('Check-in is off')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Check-in settings' })).toHaveAttribute('href', '/settings/checkin')
    expect(screen.queryByText(/Something went wrong/)).not.toBeInTheDocument()
  })

  it('tells others to ask an admin when check-in is off', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'tess', display_name: 'Tess', role: 'tech', permissions: ['floorplan.view'] } },
      'GET /api/checkins/overview': () => ({ status: 404, body: { error: 'Check-in is disabled' } }),
    }).fn)
    renderWithApp(<Checkins />, '/checkins')
    expect(await screen.findByText(/An admin can turn on seat check-in/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Check-in settings' })).not.toBeInTheDocument()
  })

  it('says no seat cards are printed instead of "0 of 0 PINs" (#1039)', async () => {
    const none = { ...data, counts: { ...data.counts, pins: 0, unused_pins: 0 } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/checkins/overview': none }).fn)
    renderWithApp(<Checkins />, '/checkins')
    expect(await screen.findByText('No seat cards with PINs yet')).toBeInTheDocument()
    expect(screen.queryByText(/of 0 seat PINs/)).not.toBeInTheDocument()
  })

  it('counts the states, lists every check-in and filters by state', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/checkins/overview': data }).fn)
    renderWithApp(<Checkins />, '/checkins')
    expect(await screen.findByText('sw-a-01 Gi1/0/2')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4)
    expect(screen.getByText('3 of 24 seat PINs used')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^State: All/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Not wired\s*1/, hidden: true }))
    await vi.waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2))
    expect(screen.getByText('Phone')).toBeInTheDocument()
  })

  it('looks for a port again and forgets a wrong one', async () => {
    const f = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/checkins/overview': data,
      'POST /api/checkins/A-3/retry': { ok: true, wired: 'pending' }, 'DELETE /api/checkins/A-2/port': { ok: true },
    })
    vi.stubGlobal('fetch', f.fn)
    renderWithApp(<Checkins />, '/checkins')
    fireEvent.click(await screen.findByRole('button', { name: 'Look for the port of A-3 again' }))
    await waitFor(() => expect(f.calls.some((c) => c.method === 'POST' && c.path === '/api/checkins/A-3/retry')).toBe(true))
    fireEvent.click(screen.getByRole('tab', { name: 'Review (1)' }))
    expect(await screen.findByText('Seat A-2 checked in on the port the patch plan gives to A-7')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Forget port of A-2' }))
    await waitFor(() => expect(f.calls.some((c) => c.method === 'DELETE' && c.path === '/api/checkins/A-2/port')).toBe(true))
  })

  it('shows what the agents asked for the captive portal', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/checkins/overview': data }).fn)
    renderWithApp(<Checkins />, '/checkins')
    fireEvent.click(await screen.findByRole('tab', { name: 'Captive portal' }))
    const table = await screen.findByRole('table')
    expect(within(table).getByText('hall-a')).toBeInTheDocument()
  })

  it('shows who sat where and filters on a clicked MAC (the history tab)', async () => {
    const session = { seat: 'A-3', username: 'nova', mac: '02:00:00:00:00:03', ips: ['192.0.2.24'], start: now - 3600, end: null,
      start_local: 'Sat 10:00', end_local: '' }
    const f = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/checkins/overview': data,
      'GET /api/checkins/history?view=sessions': { view: 'sessions', total: 1, enabled: true, rows: [session] },
      'GET /api/checkins/history?view=sessions&mac=02%3A00%3A00%3A00%3A00%3A03': { view: 'sessions', total: 1, enabled: true, rows: [session] },
    })
    vi.stubGlobal('fetch', f.fn)
    renderWithApp(<Checkins />, '/checkins')
    fireEvent.click(await screen.findByRole('tab', { name: 'History' }))
    expect(await screen.findByText('Still here')).toBeInTheDocument()
    expect(screen.getByText('1 session')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '02:00:00:00:00:03' }))
    await waitFor(() => expect(f.calls.some((c) => c.path.includes('mac=02%3A00'))).toBe(true))
    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute('href', expect.stringContaining('mac=02%3A00'))
  })

  it('says how to turn check-in on instead of failing when it is off', async () => {
    const off = () => ({ status: 404, body: { error: 'Check-in is disabled', code: 'checkin_disabled' } })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/checkins/overview': off }).fn)
    renderWithApp(<Checkins />)
    expect(await screen.findByText('Check-in is off')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Check-in settings' })).toHaveAttribute('href', '/settings/checkin')
    expect(screen.queryByRole('button', { name: /Try again/ })).not.toBeInTheDocument()
  })
})
