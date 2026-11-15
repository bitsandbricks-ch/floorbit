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
})
