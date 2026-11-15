import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StatusPageData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import NetworkStatus from './NetworkStatus'

afterEach(() => vi.unstubAllGlobals())

const at = 1_763_100_000
const data: StatusPageData = {
  state: 'degraded', auto_state: 'degraded', override: null, since: at - 300, checked_at: at,
  areas: [{ hall: '', block: 'A', rows: '1-2', seats: 2 }],
  crew_areas: [{ hall: '', block: 'A', rows: '1-2', seats: 2, switches: ['sw-a-01'] }],
  recovered: [], recovered_at: null, crew_recovered: [],
  updates: [{ id: 'u1', at: at - 60, text: 'A switch in block A is down, we are on it.', state: null, area: 'Block A' }],
  public: true, switch_names: false,
}

describe('NetworkStatus', () => {
  it('shows the state, the areas with switches for the crew, and posts updates', async () => {
    const sent: { method: string; path: string; body: unknown }[] = []
    const auth = fakeFetch({ 'GET /api/auth/me': { enabled: false } })
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/status-page')) return auth.fn(input, init)
      const method = init?.method ?? 'GET'
      if (method !== 'GET') sent.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : null })
      return new Response(JSON.stringify(method === 'GET' ? data : { ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<NetworkStatus />)
    expect(await screen.findByTestId('state')).toHaveTextContent('Part of the network down')
    expect(screen.getByText('Seat block A')).toBeInTheDocument()
    expect(screen.getByText('rows 1-2 · 2 seats · switches: sw-a-01')).toBeInTheDocument()
    expect(screen.getByText('A switch in block A is down, we are on it.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New update for attendees'), { target: { value: 'Fixed.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post' }))
    await waitFor(() => expect(sent).toContainEqual({ method: 'POST', path: '/api/status-page/updates', body: { text: 'Fixed.', area: '' } }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove update' }))
    await waitFor(() => expect(sent.some((s) => s.method === 'DELETE' && s.path === '/api/status-page/updates/u1')).toBe(true))
  })

  it('announces planned maintenance and marks the one running now (issue #422)', async () => {
    const sent: { method: string; path: string; body: unknown }[] = []
    const auth = fakeFetch({ 'GET /api/auth/me': { enabled: false } })
    const running = { id: 'm1', start: at - 600, end: at + 600, text: 'Switch swap in hall B', area: 'Hall B' }
    const later = { id: 'm2', start: at + 7200, end: at + 9000, text: 'Firewall update', area: '' }
    const withPlans = { ...data, state: 'maintenance', planned: [running, later], maintenance_now: running }
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/status-page')) return auth.fn(input, init)
      const method = init?.method ?? 'GET'
      if (method !== 'GET') sent.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : null })
      return new Response(JSON.stringify(method === 'GET' ? withPlans : { ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<NetworkStatus />)
    const box = await screen.findByTestId('planned')
    expect(box).toHaveTextContent('Switch swap in hall B')
    expect(box).toHaveTextContent('Firewall update')
    expect(screen.getAllByText('Now')).toHaveLength(1)
    const add = screen.getByRole('button', { name: 'Announce' })
    expect(add).toBeDisabled()
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2030-01-02T10:00' } })
    fireEvent.change(screen.getByLabelText('Until'), { target: { value: '2030-01-02T10:30' } })
    fireEvent.change(screen.getByLabelText('What attendees should know'), { target: { value: 'Core swap' } })
    fireEvent.click(add)
    await waitFor(() => expect(sent).toContainEqual({ method: 'POST', path: '/api/status-page/maintenance', body: {
      start: new Date('2030-01-02T10:00').getTime() / 1000, end: new Date('2030-01-02T10:30').getTime() / 1000,
      text: 'Core swap', area: '' } }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Cancel this maintenance' })[1])
    await waitFor(() => expect(sent.some((s) => s.method === 'DELETE' && s.path === '/api/status-page/maintenance/m2')).toBe(true))
  })

  it('lists the areas that are back up recently, with their switches (issue #396)', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false },
      'GET /api/status-page': { ...data, state: 'operational', auto_state: 'operational', since: null, areas: [], crew_areas: [],
        recovered: [{ hall: '', block: 'C', rows: '', seats: null }], recovered_at: at - 120,
        crew_recovered: [{ hall: '', block: 'C', rows: '', seats: null, switches: ['sw-c-02'] }] },
    }).fn)
    renderWithApp(<NetworkStatus />)
    const box = await screen.findByTestId('recovered')
    expect(box).toHaveTextContent('Back up recently')
    expect(box).toHaveTextContent('Seat block C')
    expect(box).toHaveTextContent('switches: sw-c-02')
  })

  it('offers updates to start from for areas down and back, without switch names', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false },
      'GET /api/status-page': { ...data, recovered: [{ hall: '', block: 'C', rows: '', seats: null }], recovered_at: at - 120,
        crew_recovered: [{ hall: '', block: 'C', rows: '', seats: null, switches: ['sw-c-02'] }] },
    }).fn)
    renderWithApp(<NetworkStatus />)
    const box = await screen.findByTestId('suggestions')
    expect(box).not.toHaveTextContent('sw-')
    fireEvent.click(screen.getByRole('button', { name: 'Down: Seat block A' }))
    expect(screen.getByLabelText('New update for attendees')).toHaveValue('Seat block A has no network right now. The crew is on it.')
    expect(screen.getByLabelText('Area (optional)')).toHaveValue('Seat block A')
    fireEvent.click(screen.getByRole('button', { name: 'Back: Seat block C' }))
    expect((screen.getByLabelText('New update for attendees') as HTMLTextAreaElement).value).toMatch(/^Seat block C has network again\./)
  })
})
