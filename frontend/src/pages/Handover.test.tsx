import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HandoverData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Handover from './Handover'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }
const counts = { open: 1, opened: 2, fixed: 1, outages: 1, still_down: 1, changes: 1, problems: 3 }
const now = 1_763_100_000
const data: HandoverData = {
  since: now - 3600, now, discord: true,
  previous: { id: 'h1', at: now - 3600, since: now - 7200, by: 'Ben', note: 'Row B switch is flaky.', counts },
  incidents: {
    open: [{ id: 'i1', title: 'No link', where: { kind: 'seat', name: 'A-1' }, status: 'open', assignee: null, team: null, created_at: now - 60, fixed_at: null, match: 'Main stage' }],
    opened: 2,
    fixed: [{ id: 'i2', title: 'Slow', where: { kind: 'seat', name: 'A-2' }, status: 'fixed', assignee: 'ana', team: null, created_at: now - 600, fixed_at: now - 30, match: null }],
  },
  outages: [{ switch_id: 's1', name: 'sw-b-01', down_at: now - 120, back_at: null, down_s: 120 }],
  changes: [{ at: now - 300, user: 'lea', area: 'ports', action: 'Bounced port', target: 'A-1' }],
  counts,
  history: [{ id: 'h1', at: now - 3600, since: now - 7200, by: 'Ben', note: 'Row B switch is flaky.', counts }],
}

describe('Shift handover', () => {
  it('shows the shift and hands over with a note', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/handover': data,
      'POST /api/handover': () => ({ status: 201, body: { ...data.previous, id: 'h2', posted: true } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Handover />)
    expect(await screen.findByText('Row B switch is flaky.')).toBeInTheDocument()
    expect(screen.getByText('No link')).toBeInTheDocument()
    expect(screen.getByText('Main stage')).toBeInTheDocument()
    expect(screen.getByText('sw-b-01')).toBeInTheDocument()
    expect(screen.getByText('Bounced port: A-1')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: /Note for the next shift/ }), { target: { value: 'Watch row B' } })
    fireEvent.click(screen.getByRole('button', { name: 'Hand over' }))
    expect(await screen.findByText(/posted to Discord/)).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && JSON.stringify(c.body) === JSON.stringify({ note: 'Watch row B', discord: true }))).toBe(true))
  })
})
