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
  it('counts the states, lists every check-in and filters by state', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/checkins/overview': data }).fn)
    renderWithApp(<Checkins />, '/checkins')
    expect(await screen.findByText('sw-a-01 Gi1/0/2')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4)
    expect(screen.getByText('3 of 24 seat PINs used')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Not wired · 1/ }))
    expect(screen.getAllByRole('row')).toHaveLength(2)
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
})
