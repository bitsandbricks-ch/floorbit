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
  it('the state picker starts on Automatic, and the area offers halls and blocks', async () => {
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
    // Nothing set by hand: the picker says Automatic, and Set waits for a change.
    const picker = screen.getByDisplayValue('Automatic: Part of the network down')
    const set = screen.getByRole('button', { name: 'Set' })
    expect(set).toBeDisabled()
    fireEvent.click(picker)
    fireEvent.click(await screen.findByRole('option', { name: 'Network outage', hidden: true }))
    expect(set).toBeEnabled()
    fireEvent.click(set)
    await waitFor(() => expect(sent).toContainEqual({ method: 'PUT', path: '/api/status-page/override', body: { state: 'outage', note: '' } }))

    // Planned maintenance has an area field of its own; the update's is the one with a list.
    const area = screen.getAllByLabelText('Area (optional)').find((e) => e.hasAttribute('aria-haspopup'))!
    fireEvent.focus(area)
    fireEvent.click(area)
    expect(await screen.findByRole('option', { name: 'Main hall', hidden: true })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Seat block A', hidden: true })).toBeInTheDocument()
  })

  it('lifts a state set by hand by choosing Automatic (#890)', async () => {
    const sent: { method: string; body: unknown }[] = []
    const rest = fakeFetch({ 'GET /api/auth/me': { enabled: false }, 'GET /api/options/halls': { options: [] }, 'GET /api/options/blocks': { options: [] } })
    const pinned = { ...data, state: 'maintenance', override: { state: 'maintenance', note: '', by: 'lead', at: 1_763_100_000 } }
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!String(input).startsWith('/api/status-page')) return rest.fn(input, init)
      const method = init?.method ?? 'GET'
      if (method !== 'GET') sent.push({ method, body: JSON.parse(String(init?.body)) })
      return new Response(JSON.stringify(method === 'GET' ? pinned : { ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<NetworkStatus />)
    fireEvent.click(await screen.findByDisplayValue('Maintenance'))
    fireEvent.click(await screen.findByRole('option', { name: 'Automatic: Part of the network down', hidden: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Set' }))
    await waitFor(() => expect(sent).toContainEqual({ method: 'PUT', body: { state: null, note: '' } }))
  })
})
