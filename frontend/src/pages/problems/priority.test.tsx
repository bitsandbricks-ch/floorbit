import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { rowAction, rowActions } from '@/test/rowMenu'
import Problems from '../Problems'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const list: ProblemList = {
  problems: [
    // The server sends them urgent first; the page sorts the same way.
    { id: 'switch:c1', kind: 'switch', level: 'down', title: 'core-01 is offline', where: 'core-01', since: now - 60, link: '', switch_id: 'c1',
      priority: 1, hall: 'Hall 2', tags: ['core'] },
    { id: 'switch:a1', kind: 'switch', level: 'down', title: 'sw-a-01 is offline', where: 'sw-a-01', since: now - 600, link: '', switch_id: 'a1',
      priority: 2, hall: 'Hall 1', tags: ['row-a'] },
    { id: 'power:p1', kind: 'power', level: 'warn', title: 'Circuit near its limit', where: 'B row 2', since: now - 900, link: '',
      mute_id: 'problem:power:p1', priority: 1, raised: { by: 'kim', at: now }, hall: 'Hall 1' },
  ],
  counts: { down: 2, warn: 1, muted: 0 },
  mutes: [], quiet_hours: false, checked_at: now, can_mute: true,
}
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }
const rows = () => screen.queryAllByRole('row').filter((r) => r.closest('tbody'))

describe('Problem priorities (issue #1364)', () => {
  it('puts urgent and raised problems first and marks them', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list }).fn)
    renderWithApp(<Problems />)
    await screen.findByRole('row', { name: 'core-01 is offline' })
    expect(rows().map((r) => r.getAttribute('aria-label'))).toEqual(['Circuit near its limit', 'core-01 is offline', 'sw-a-01 is offline'])
    expect(within(screen.getByRole('row', { name: 'core-01 is offline' })).getByText('Urgent')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: 'Circuit near its limit' })).getByText('Raised')).toBeInTheDocument()
  })

  it('raises one by hand and lowers a raised one', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list, 'POST /api/alerts/raised': { ok: true },
      'DELETE /api/alerts/raised/power%3Ap1': { ok: true } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Problems />)
    const access = await screen.findByRole('row', { name: 'sw-a-01 is offline' })
    await rowAction(access, 'Raise')
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'POST', path: '/api/alerts/raised', body: { problem_id: 'switch:a1' } }))
    expect(await rowActions(screen.getByRole('row', { name: 'core-01 is offline' }))).not.toContain('Raise')
    await rowAction(screen.getByRole('row', { name: 'Circuit near its limit' }), 'Lower again')
    await waitFor(() => expect(api.calls.some((c) => c.method === 'DELETE' && c.path.startsWith('/api/alerts/raised/'))).toBe(true))
  })

  it('groups by hall and filters by tag', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list }).fn)
    renderWithApp(<Problems />, '/problems?group=hall')
    expect(await screen.findByRole('button', { name: /^Hall 1/ })).toBeInTheDocument()
    const hall2 = screen.getByRole('button', { name: /^Hall 2/ }).closest('tbody')!
    expect(within(hall2).getByRole('row', { name: 'core-01 is offline' })).toBeInTheDocument()
  })

  it('filters by a switch tag from the address', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list }).fn)
    renderWithApp(<Problems />, '/problems?tag=row-a')
    await screen.findByRole('row', { name: 'sw-a-01 is offline' })
    expect(rows()).toHaveLength(1)
  })
})
