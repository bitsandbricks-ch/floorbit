import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HandoverData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Handover from './Handover'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }
const counts = { open: 1, opened: 2, fixed: 1, outages: 1, still_down: 1, changes: 1, problems: 3 }
const now = 1_763_100_000
const data: HandoverData = {
  since: now - 3600, now, discord: true,
  previous: { id: 'h1', at: now - 3600, since: now - 7200, by: 'Ben', note: 'Row B switch is flaky.', counts },
  incidents: {
    open: [{ id: 'i1', title: 'No link', where: { kind: 'seat', name: 'A-1' }, status: 'open', assignee: null, team: null, created_at: now - 60, fixed_at: null }],
    opened: 2,
    fixed: [{ id: 'i2', title: 'Slow', where: { kind: 'seat', name: 'A-2' }, status: 'fixed', assignee: 'ana', team: null, created_at: now - 600, fixed_at: now - 30 }],
  },
  outages: [{ switch_id: 's1', name: 'sw-b-01', down_at: now - 120, back_at: null, down_s: 120 }],
  changes: [{ at: now - 300, user: 'lea', area: 'ports', action: 'Bounced port', target: 'A-1' }],
  seat_notes: [{ seat: 'C-3', text: 'Cable swapped, watch it', by: 'ana', at: now - 200 }],
  counts,
  history: [{ id: 'h1', at: now - 3600, since: now - 7200, by: 'Ben', note: 'Row B switch is flaky.', counts }],
}

describe('Shift handover', () => {
  it('leaves the seat notes out when the shift wrote none', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': { ...data, seat_notes: [] } }).fn)
    renderWithApp(<Handover />)
    expect(await screen.findByText('Row B switch is flaky.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Seat notes from this shift' })).toBeNull()
  })

  it('shows the shift and hands over with a note', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/handover': data,
      'POST /api/handover': () => ({ status: 201, body: { ...data.previous, id: 'h2', posted: true } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Handover />)
    expect(await screen.findByText('Row B switch is flaky.')).toBeInTheDocument()
    expect(screen.getByText('No link')).toBeInTheDocument()
    expect(screen.getByText('sw-b-01')).toBeInTheDocument()
    expect(screen.getByText('Bounced port: A-1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Seat notes from this shift' })).toBeInTheDocument()
    expect(screen.getByText('Cable swapped, watch it')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'C-3' })).toHaveAttribute('href', '/plan?seat=C-3')
    fireEvent.change(screen.getByRole('textbox', { name: /Note for the next shift/ }), { target: { value: 'Watch row B' } })
    fireEvent.click(screen.getByRole('button', { name: 'Hand over' }))
    expect(await screen.findByText(/posted to Discord/)).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && JSON.stringify(c.body) === JSON.stringify({ note: 'Watch row B', discord: true }))).toBe(true))
  })

  it('copies the summary as text, with the note being written (issue #220)', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': data }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    fireEvent.change(await screen.findByLabelText(/Note for the next shift/), { target: { value: 'Watch row B' } })
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    const text = writeText.mock.calls[0][0] as string
    expect(text).toMatch(/^Shift handover: Since /)
    expect(text).toContain('Incidents open: 1 · New this shift: 2 · Fixed this shift: 1 · Switch outages: 1 · Problems now: 3')
    expect(text).toContain('Still open:\n- No link (Seat A-1)')
    expect(text).toContain('Fixed this shift:\nBy: ana 1\n- Slow (Seat A-2, ana)')
    expect(text).toMatch(/Switch outages:\n- sw-b-01: down since .+ \(2 min\)/)
    expect(text.endsWith('Note for the next shift:\nWatch row B')).toBe(true)
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('says what is muted and which crew notice is up (issue #258)', async () => {
    const extra = {
      mutes: [{ kind: 'switch' as const, name: 'sw-a-01', until: now + 3600, by: 'kim', reason: 'Swapping the PSU' },
        { kind: 'health' as const, name: 'DNS', until: now + 600, by: 'ana', reason: '' }],
      notice: { text: 'Row C has no power until 14:00', level: 'warn' as const, until: null, by: 'kim', at: now },
    }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': { ...data, ...extra } }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    expect(await screen.findByText(/Row C has no power until 14:00/)).toBeInTheDocument()
    const muted = screen.getByRole('heading', { name: 'Muted right now' }).parentElement!
    expect(within(muted).getByRole('link', { name: 'sw-a-01' })).toHaveAttribute('href', '/plan?switch=sw-a-01')
    expect(within(muted).getByRole('link', { name: 'DNS' })).toHaveAttribute('href', '/health')
    expect(within(muted).getByText(/Swapping the PSU/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    const text = writeText.mock.calls[0][0] as string
    expect(text).toContain('Crew notice up: Row C has no power until 14:00')
    expect(text).toMatch(/Muted right now:\n- sw-a-01, muted until .+ by kim \(Swapping the PSU\)\n- DNS, muted until .+ by ana/)
  })
  it('says how fast this shift fixed things (issue #334)', async () => {
    const fast = { ...data, counts: { ...counts, median_fix_s: 14 * 60 } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': fast }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    expect(await screen.findByText('half within 14 min')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    expect(writeText.mock.calls[0][0]).toContain('Fixed this shift: 1 (half within 14 min) · Switch outages: 1')
  })
  it('says who fixed how many (issue #348)', async () => {
    const i = data.incidents.fixed[0]
    const fixed = [i, { ...i, id: 'i3', assignee: 'kim' }, { ...i, id: 'i4', assignee: 'kim' }, { ...i, id: 'i5', assignee: null }]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech,
      'GET /api/handover': { ...data, incidents: { ...data.incidents, fixed } } }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    expect(await screen.findByText('By: kim 2 · ana 1 · nobody named 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    expect(writeText.mock.calls[0][0]).toContain('Fixed this shift:\nBy: kim 2 · ana 1 · nobody named 1\n- Slow')
  })
  it('lists what the programme has coming up this shift (issue #432)', async () => {
    const at = Math.floor(Date.now() / 1000) + 3600
    const extra = { coming_up: [
      { id: 'f', title: 'Rocket Cup final', kind: 'tournament', start: at, end: null, where: 'Main stage' },
      { id: 'p', title: 'Znacht: pizza', kind: 'meal', start: at + 1800, end: null, where: null },
    ] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': { ...data, ...extra } }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    const box = (await screen.findByRole('heading', { name: 'Coming up this shift' })).parentElement!
    expect(within(box).getByText('Rocket Cup final')).toBeInTheDocument()
    expect(within(box).getByText('Tournament')).toBeInTheDocument()
    expect(within(box).getByRole('link', { name: 'Whole programme' })).toHaveAttribute('href', '/schedule')
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    expect(writeText.mock.calls[0][0]).toMatch(/Coming up this shift:\n- .+ Rocket Cup final \(Main stage\)\n- .+ Znacht: pizza/)
  })
  it('marks incidents that have waited 10 minutes with nobody on them', async () => {
    const waiting: HandoverData = { ...data, counts: { ...counts, open: 2, waiting: 1 }, incidents: { ...data.incidents, open: [
      { ...data.incidents.open[0], id: 'w1', title: 'Old one', created_at: now - 25 * 60 },
      data.incidents.open[0],
    ] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/handover': waiting }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<Handover />)
    expect(await screen.findByText('Waiting 25 min')).toBeInTheDocument()
    expect(screen.getAllByText(/^Waiting/)).toHaveLength(1)   // the one opened a minute ago is not
    expect(screen.getByText('1 waiting 10+ min')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    expect(writeText.mock.calls[0][0]).toContain(': 2 (1 waiting 10+ min) · ')
  })
})
