import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Teardown as TeardownData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Teardown from './Teardown'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const at = 1_763_100_000
const data: TeardownData = {
  done: false, left: 3, total: 4,
  parts: {
    gear: { done: false, left: 1, out: [{ id: 'g1', name: 'sw-spare-01', to: 'tech-ana', at }] },
    configs: { done: false, left: 1, switches: [{ id: 's1', name: 'sw-a-01', archived: null }, { id: 's2', name: 'sw-b-01', archived: { by: 'Lea', at } }] },
    export: { done: false, left: 1, last: null },
    custom: { done: true, left: 0, items: [] },
  },
}

describe('Teardown', () => {
  it('shows what is left, ticks a switch and adds a step', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/teardown': data,
      'PUT /api/teardown/switches/s1': { ...data, left: 2 },
      'POST /api/teardown/items': { ...data, parts: { ...data.parts, custom: { done: false, left: 1, items: [{ id: 'i1', text: 'Return the rented switches', added_by: 'Lea', added_at: at, done_by: null, done_at: null }] } } },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Teardown />)
    expect(await screen.findByText('3 things left')).toBeInTheDocument()
    expect(screen.getByText('sw-spare-01')).toBeInTheDocument()
    expect(screen.getByText(/An admin downloads the export/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'sw-a-01' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT' && JSON.stringify(c.body) === '{"done":true}')).toBe(true))
    fireEvent.change(screen.getByRole('textbox', { name: 'New step' }), { target: { value: 'Return the rented switches' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Return the rented switches')).toBeInTheDocument()
  })
})
