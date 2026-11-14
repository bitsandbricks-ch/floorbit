import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventFigures, EventsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Events from './Events'
import { share } from './events/metrics'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const figures = (over: Partial<EventFigures>): EventFigures => ({
  seats: 400, online_max: 350, checked_in_max: 380, peak_bps: 4e9, bytes_moved: 12e12, hours: 48, incidents: 12,
  incidents_fixed: 12, from_seats: 5, median_fix_s: 900, outages: 2, down_s: 600, problem_ports: 3, cache_saved_bytes: null, ...over,
})
const data: EventsData = {
  current: { name: 'Example LAN 2026', start: 1_763_100_000, end: 1_763_200_000, figures: figures({ incidents: 4 }) },
  archived: [{ id: '20251101-0a1b2c3d', name: 'Example LAN 2025', start: 1_730_000_000, end: 1_730_150_000, archived_at: 1_730_200_000,
    archived_by: 'Ada', figures: figures({ online_max: 300 }) }],
}

describe('Events', () => {
  it('compares the running event with past ones and closes it after the name is typed', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/past-events': data,
      'POST /api/past-events/close': { archived: data.archived[0], started: 1 },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Events />)
    expect(await screen.findAllByText('Example LAN 2025')).toHaveLength(2)
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('350')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Floor plan' })).toHaveAttribute('href', '/api/past-events/backup/20251101-0a1b2c3d.json')

    const close = screen.getByRole('button', { name: 'Close the event' })
    expect(close).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Type "Example LAN 2026" to confirm' }), { target: { value: 'example lan 2026' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Name of the next event/ }), { target: { value: 'Example LAN 2027' } })
    fireEvent.click(close)
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/past-events/close'
      && JSON.stringify(c.body) === '{"confirm":"example lan 2026","next_name":"Example LAN 2027"}')).toBe(true))
    expect(await screen.findByText(/is closed and kept/)).toBeInTheDocument()
  })

  it('shows viewers the comparison and reports, without admin actions', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/past-events': data }).fn)
    renderWithApp(<Events />)
    expect(await screen.findByRole('link', { name: 'Report' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close the event' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Floor plan' })).not.toBeInTheDocument()
  })

  it('scales the bars to the largest value in the row', () => {
    expect(share(50, [50, 100, null])).toBe(50)
    expect(share(null, [null, null])).toBe(0)
  })
})
