import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ScheduleData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Schedule from './Schedule'
import { fromInput, toInput } from './schedule/time'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const t0 = fromInput('2030-03-17T10:00')
const data: ScheduleData = {
  event: { start: t0, end: null }, public: true, kinds: ['talk', 'tournament', 'meal', 'quiet', 'other'],
  items: [
    { id: 'a', title: 'Opening keynote', kind: 'talk', start: t0, end: t0 + 1800, where: 'Main stage', note: '', source: 'ical', uid: 'x', updated_at: 1, by: 'lea' },
    { id: 'b', title: 'Lunch', kind: 'meal', start: t0 + 3 * 3600, end: null, where: '', note: '', source: 'floorbit', uid: null, updated_at: 1, by: 'lea' },
  ],
}

describe('schedule time inputs', () => {
  it('round-trips local time', () => {
    expect(toInput(t0)).toBe('2030-03-17T10:00')
  })
})

describe('Schedule page', () => {
  it('lists the items by day and adds one', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/schedule': data, 'POST /api/schedule/items': { ...data.items[1], id: 'c' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Schedule />)
    expect(await screen.findByText('Opening keynote')).toBeInTheDocument()
    expect(screen.getByText('iCal')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '/agenda' })).toHaveAttribute('href', '/agenda')
    fireEvent.click(screen.getByRole('button', { name: 'Add item' }))
    fireEvent.change(screen.getByLabelText(/^Title/), { target: { value: 'Group photo' } })
    fireEvent.change(screen.getByLabelText(/^Starts/), { target: { value: '2030-03-17T16:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls).toContainEqual({
      method: 'POST', path: '/api/schedule/items',
      body: { title: 'Group photo', kind: 'other', start: fromInput('2030-03-17T16:00'), end: null, where: '', note: '' },
    }))
  })

  it('is read-only for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/schedule': { ...data, public: false } }).fn)
    renderWithApp(<Schedule />)
    expect(await screen.findByText('Lunch')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add item' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Remove Lunch' })).toBeNull()
    expect(screen.getByText(/public schedule page is off/)).toBeInTheDocument()
  })
})
