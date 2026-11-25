import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StatusPageData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import NetworkStatus from './NetworkStatus'

afterEach(() => vi.unstubAllGlobals())

const data: StatusPageData = {
  state: 'degraded', auto_state: 'degraded', override: null, since: null, checked_at: 1_763_100_000,
  areas: [], crew_areas: [], recovered: [], recovered_at: null, crew_recovered: [], updates: [], public: true,
}

describe('NetworkStatus pickers (#1416)', () => {
  it('starts the state picker on the state shown, and offers halls and blocks for the area', async () => {
    const sent: { method: string; path: string; body: unknown }[] = []
    const rest = fakeFetch({
      'GET /api/auth/me': { enabled: false },
      'GET /api/options/halls': { options: [{ value: 'main', label: 'Main hall' }] },
      'GET /api/options/blocks': { options: [{ value: 'b1', label: 'A' }] },
    })
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/status-page')) return rest.fn(input, init)
      const method = init?.method ?? 'GET'
      if (method !== 'GET') sent.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : null })
      return new Response(JSON.stringify(method === 'GET' ? data : { ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<NetworkStatus />)
    await screen.findByTestId('state')
    expect(screen.getByDisplayValue('Part of the network down')).toBeInTheDocument()
    const set = screen.getByRole('button', { name: 'Set' })
    expect(set).toBeEnabled()
    fireEvent.click(set)
    await waitFor(() => expect(sent).toContainEqual({ method: 'PUT', path: '/api/status-page/override', body: { state: 'degraded', note: '' } }))

    // Planned maintenance has an area field of its own; the update's is the one with a list.
    const area = screen.getAllByLabelText('Area (optional)').find((e) => e.hasAttribute('aria-haspopup'))!
    fireEvent.focus(area)
    fireEvent.click(area)
    expect(await screen.findByRole('option', { name: 'Main hall', hidden: true })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Seat block A', hidden: true })).toBeInTheDocument()
  })
})
