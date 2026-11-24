import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SwitchArea, SwitchAreas as Areas } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import SwitchAreas from './SwitchAreas'

afterEach(() => vi.unstubAllGlobals())

const crew = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'seats.view', 'seats.edit'] } }
const none = { blocks: [], rows: [], seats: [], exclude: false }
const sw = (name: string, extra: Partial<SwitchArea>): SwitchArea => ({
  name, id: name, how: 'todo', serves: { blocks: [], rows: [], seats: [] }, manual: none, learned: [], plan_blocks: [],
  todo: false, drift: [], suggest: [], ...extra,
})
const AREAS: Areas = {
  blocks: [{ id: 'b1', label: 'A' }],
  switches: [
    sw('sw-a-01', { how: 'learned', serves: { blocks: [], rows: ['b1:1'], seats: ['A-1', 'A-2', 'A-5'] },
      learned: [{ seat: 'A-1', source: 'walk' }], suggest: [{ id: 'b1:1', name: '1', block_label: 'A' }] }),
    sw('sw-a-02', { how: 'plan', serves: { blocks: ['b1'], rows: [], seats: [] }, plan_blocks: ['b1'],
      drift: [{ kind: 'learned_outside_plan', seats: ['B-3'] }] }),
    sw('dist-01', { how: 'todo', todo: true }),
  ],
}

describe('SwitchAreas', () => {
  it('shows where each switch gets its seats, the disagreements, and pins a learned row in one click', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': crew, 'GET /api/switch-areas': AREAS, 'PUT /api/switch-areas/sw-a-01': { ...none, rows: ['b1:1'] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SwitchAreas />, '/switch-areas')
    expect(await screen.findByText('Block A')).toBeInTheDocument()
    expect(screen.getByText('Learned outside the block it is drawn in: B-3')).toBeInTheDocument()
    expect(screen.getByText(/1 switch serves no seats yet/)).toBeInTheDocument()
    expect(screen.getByText('3 seats')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pin row A 1' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ ...none, rows: ['b1:1'] }))
  })
})
