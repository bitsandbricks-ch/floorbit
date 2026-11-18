import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PortArea } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PortAreas } from './PortAreas'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: false }
const area = (id: string, first: number, start: number): PortArea => ({
  id, switch: 'sw-a-01', first, last: first + 9, seats: Array.from({ length: 10 }, (_, i) => `A-${start + i}`),
  label: `A-${start}..A-${start + 9}`,
})

describe('PortAreas', () => {
  it('lists the areas per switch and saves a quick entry in batches', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/port-areas': { areas: [area('p1', 1, 1), area('p2', 11, 11)] },
      'POST /api/port-areas/batch': (init?: RequestInit) => ({ body: { areas: JSON.parse(String(init?.body)).dry_run ? [] : [] } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PortAreas canEdit switches={['sw-a-01', 'sw-b-01']} />)
    expect(await screen.findByText('1-10 → A-1..A-10')).toBeInTheDocument()
    expect(screen.getByText('11-20 → A-11..A-20')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add port areas' }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Switch' }), { target: { value: 'sw-b-01' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Ports 1-10: first seat' }), { target: { value: 'B-1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Ports 21-30: first seat' }), { target: { value: 'b-11' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save areas' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Save areas' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && !(c.body as { dry_run?: boolean }).dry_run
      && JSON.stringify((c.body as { starts: string[] }).starts) === JSON.stringify(['B-1', '', 'b-11', '']))).toBe(true))
  })

  it('removes one area', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/port-areas': { areas: [area('p1', 1, 1)] },
      'DELETE /api/port-areas/p1': { ok: true } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PortAreas canEdit switches={[]} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Remove the area A-1..A-10' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'DELETE')).toBe(true))
  })
})
