import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { QosHints, TournamentData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Tournament from './Tournament'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const cells = ['B-1', 'B-2', 'A-1'].map((seat, i) => ({ seat, x: i * 32 - 48, y: -16, hit: false, on: seat.startsWith('B') }))
const data: TournamentData = {
  zones: [{ id: 'z1', name: 'Main stage', blocks: ['B'], seats: [], note: 'Finals on Sunday' }],
  seats: { 'B-1': 'Main stage', 'B-2': 'Main stage' },
  plans: [{ hall: 'main', name: 'Main hall', match: 2, drawing: { shapes: [{ cx: 400, cy: 300, rotation: 0, w: 96, h: 32, name: 'B', cells }], box: '0 0 800 600', cell: 32 } }],
}
const qos: QosHints = { available: true, missing: ['B-2'], switches: [{ switch: 'sw-b-01', switch_id: 's1', uplinks: ['Te1/1/1'], ports: [{ port: 'Gi1/0/1', seat: 'B-1', zone: 'Main stage' }] }] }

describe('Tournament seats', () => {
  it('shows the zones, the plan and the QoS ports, and adds a zone', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/tournament': data, 'GET /api/tournament/qos': qos,
      'POST /api/tournament/zones': { status: 201, body: { id: 'z2', name: 'Side stage', blocks: [], seats: ['A-1'], note: '' } },
    })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<Tournament />)
    expect(await screen.findByText('Main stage')).toBeInTheDocument()
    expect(screen.getByText('block B')).toBeInTheDocument()
    expect(container.querySelectorAll('.cell.match')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Look up ports' }))
    expect(await screen.findByText('Gi1/0/1')).toBeInTheDocument()
    expect(screen.getByText('Not found on any port: B-2')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Side stage' } })
    fireEvent.change(screen.getByRole('textbox', { name: /^Seats/ }), { target: { value: 'A-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add zone' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'Side stage', seats: 'A-1', note: '' }))
  })

  it('is read-only for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/tournament': data }).fn)
    renderWithApp(<Tournament />)
    expect(await screen.findByText('Main stage')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Add zone' })).toBeNull())
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull()
  })
})
