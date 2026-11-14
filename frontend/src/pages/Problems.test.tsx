import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Problems from './Problems'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const list = (over: Partial<ProblemList> = {}): ProblemList => ({
  problems: [
    { id: 'switch:s1', kind: 'switch', level: 'down', title: 'sw-c-02 is offline', where: 'sw-c-02', since: now - 300, link: '/', switch_id: 's1', muted: null },
    { id: 'power:c1', kind: 'power', level: 'warn', title: 'Circuit B row 2 getting close (86.9 %)', where: 'Feeds 12 seats', since: now, link: '/power' },
    { id: 'switch:s2', kind: 'switch', level: 'down', title: 'sw-d-01 is offline', where: 'sw-d-01', since: now - 60, link: '/', switch_id: 's2',
      muted: { until: now + 3600, by: 'kim', reason: 'Recabling' } },
  ],
  counts: { down: 1, warn: 1, muted: 1 },
  mutes: [{ switch_id: 's2', name: 'sw-d-01', until: now + 3600, at: now, by: 'kim', reason: 'Recabling' }],
  quiet_hours: false, checked_at: now, can_mute: true, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }

describe('Problems', () => {
  it('lists what is wrong, worst first, with mutes', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list() }).fn)
    renderWithApp(<Problems />)
    const sw = await screen.findByRole('article', { name: 'sw-c-02 is offline' })
    expect(within(sw).getByText('Switch')).toBeInTheDocument()
    expect(screen.getByText('1 down')).toBeInTheDocument()
    expect(screen.getByText('1 muted')).toBeInTheDocument()
    const muted = screen.getByRole('article', { name: 'sw-d-01 is offline' })
    expect(within(muted).queryByRole('button', { name: 'Mute' })).not.toBeInTheDocument()
    expect(within(muted).getByText(/Recabling/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Muted switches' })).toBeInTheDocument()
  })

  it('lists ports that need attention, linked to the floor plan', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({
      attention: [
        { id: 'attention:checkin:s1:Gi1/0/12', kind: 'checkin', level: 'warn', title: 'Seat A-12 is online without a check-in',
          where: 'sw-a-01 Gi1/0/12 (seat A-12)', since: now, link: '/?seat=A-12', switch_id: 's1' },
        { id: 'attention:flapping:s1:Gi1/0/9', kind: 'flapping', level: 'warn', title: 'Port flapping: 4 link changes in 10 minutes',
          where: 'sw-a-01 Gi1/0/9', since: now - 120, link: '/?switch=s1', switch_id: 's1' },
      ],
    }) }).fn)
    renderWithApp(<Problems />)
    const section = await screen.findByRole('region', { name: 'Needs attention' })
    const items = within(section).getAllByRole('article')
    expect(items.map((a) => a.getAttribute('aria-label'))).toEqual([
      'Seat A-12 is online without a check-in', 'Port flapping: 4 link changes in 10 minutes'])
    expect(within(items[0]).getByText('Check-in')).toBeInTheDocument()
    expect(within(items[1]).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/?switch=s1')
    expect(within(section).queryByRole('button', { name: 'Mute' })).not.toBeInTheDocument()
  })

  it('mutes a switch for the chosen time', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list(), 'POST /api/alerts/mutes': { status: 201, body: {} } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    const sw = await screen.findByRole('article', { name: 'sw-c-02 is offline' })
    fireEvent.click(within(sw).getByRole('button', { name: 'Mute' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: 'Swapping the PSU' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mute' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path === '/api/alerts/mutes')?.body)
      .toEqual({ switch_id: 's1', minutes: 60, reason: 'Swapping the PSU' }))
  })

  it('says when all is well', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ problems: [], mutes: [], counts: { down: 0, warn: 0, muted: 0 } }) }).fn)
    renderWithApp(<Problems />)
    expect(await screen.findByText('Nothing is wrong right now.')).toBeInTheDocument()
  })
})
