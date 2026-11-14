import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BracketMatch, BracketsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Brackets from './Brackets'
import { roundName } from './tournament/brackets'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const m = (id: string, a: string | null, b: string | null, extra: Partial<BracketMatch> = {}): BracketMatch => ({
  id, a: { name: a, score: null }, b: { name: b, score: null }, status: 'waiting', winner: null, seats: [], station: '', zones: [], ...extra,
})
const data: BracketsData = {
  zones: [{ id: 'z1', name: 'Main stage' }], sources: ['Demo data'], public: true,
  brackets: [{
    id: 'b1', name: 'Rocket Cup', zone_id: 'z1', source: 'floorbit', plugin: null, updated_at: 1, by: 'lea',
    rounds: [
      [m('r1m1', 'Team Aurora', 'Lag Busters', { status: 'live', seats: ['A-1', 'A-2'], zones: ['Main stage'], station: 'Stage' }),
        m('r1m2', 'Pixel Foxes', 'Byte Club', { winner: 'a', status: 'done', a: { name: 'Pixel Foxes', score: 2 }, b: { name: 'Byte Club', score: 0 } })],
      [m('r2m1', null, 'Pixel Foxes')],
    ],
  }],
}

describe('round names', () => {
  it('names the last three rounds', () => {
    expect([0, 1, 2, 3].map((r) => roundName(r, 4))).toEqual(['brackets.round', 'brackets.quarter', 'brackets.semi', 'brackets.final'])
  })
})

describe('Brackets page', () => {
  it('shows the bracket and enters a result', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/tournament/brackets': data,
      'PATCH /api/tournament/brackets/b1/matches/r1m1': data.brackets[0],
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Brackets />)
    expect(await screen.findByText('Rocket Cup')).toBeInTheDocument()
    expect(screen.getByText('Semi-finals')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'A-1' })).toHaveAttribute('href', '/?seat=A-1')
    expect(screen.getByRole('link', { name: 'Main stage' })).toHaveAttribute('href', '/tournament')
    expect(screen.getByRole('button', { name: 'Import from Demo data' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Enter the result of Team Aurora against Lag Busters' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Team Aurora' }), { target: { value: '2' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Lag Busters' }), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Team Aurora' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls).toContainEqual({
      method: 'PATCH', path: '/api/tournament/brackets/b1/matches/r1m1',
      body: { a_score: 2, b_score: 1, winner: 'a', status: 'live', seats: 'A-1, A-2', station: 'Stage' },
    }))
  })

  it('is read-only for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/tournament/brackets': data }).fn)
    renderWithApp(<Brackets />)
    expect(await screen.findByText('Rocket Cup')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Enter the result/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New bracket' })).toBeNull()
  })
})
