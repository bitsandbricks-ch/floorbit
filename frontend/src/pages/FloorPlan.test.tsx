import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatDetails, SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import FloorPlan from './FloorPlan'
import { density, findSeat, heatColor, heatLevel, matches, parseBox, seatCenter, zoom } from './plan/model'

afterEach(() => vi.unstubAllGlobals())

const cells = ['D-1', 'D-2', 'D-3', 'D-4'].map((seat, i) => ({ x: i * 32 - 64, y: -16, hit: false, seat, on: null }))
const drawing = { shapes: [{ cx: 640, cy: 500, rotation: 0, w: 128, h: 32, name: 'D', cells }], box: '544 420 192 128', cell: 32 }
const data: SeatViewData = {
  halls: [{ id: 'main', name: 'Hall' }], hall: 'main', drawing, size: { w: 1600, h: 1000, cell: 32 }, background: null, switches: [],
  seats: {
    'D-1': { state: 'online', checked_in: true, bps: 6_000_000 },
    'D-2': { state: 'offline', problems: 1, taken: true },
    'D-3': { state: 'unknown' },
    'D-4': { state: 'online', match: 'Main stage' },
  },
  blocks: [{ name: 'D', seats: 4, online: 2, problems: 1 }], monitoring: true, checkin: true, last_read: 1_800_000_000,
}
const details: SeatDetails = {
  seat: 'D-2', block: 'D', state: 'offline', bps: null, switch: 'sw-d-01', port: 'Gi1/0/2',
  incidents: [{ id: 'i1', title: 'No link', status: 'open', created_at: 1_800_000_000 }], attention: [],
  match: null, checked_in: false, last_read: 1_800_000_000, people: false,
}
const me = { enabled: true, user: { username: 'tia', display_name: 'Tia', role: 'tech', permissions: ['floorplan.view'] } }

describe('seat map model', () => {
  it('picks the level of detail from the size of a seat on screen', () => {
    const view = parseBox('0 0 1000 500')
    expect(density(32, view, { w: 200, h: 100 })).toBe('far')     // 6 px a seat
    expect(density(32, view, { w: 500, h: 250 })).toBe('mid')     // 16 px
    expect(density(32, view, { w: 1000, h: 500 })).toBe('near')   // 32 px
    expect(density(32, view, { w: 0, h: 0 })).toBe('mid')
  })

  it('zooms around the pointer and never past the limits', () => {
    const fit = parseBox('0 0 1000 500')
    const z = zoom(fit, 2, { x: 1000, y: 500 }, fit)
    expect(z).toEqual({ x: 500, y: 250, w: 500, h: 250 })
    expect(zoom(fit, 100, { x: 0, y: 0 }, fit).w).toBe(120)
    expect(zoom(fit, 0.01, { x: 0, y: 0 }, fit).w).toBe(2000)
  })

  it('finds seats however they are typed and places them on the plan', () => {
    expect(findSeat('d6', { 'D-6': 1 })).toBe('D-6')
    expect(findSeat(' d-06 ', { 'D-6': 1 })).toBe('D-6')
    expect(findSeat('Z-1', { 'D-6': 1 })).toBeNull()
    expect(seatCenter(drawing, 'D-1')).toEqual({ x: 592, y: 500 })
    expect(matches(data.seats['D-2'], 'problems') && !matches(data.seats['D-1'], 'offline')).toBe(true)
  })
})

describe('traffic overlay', () => {
  it('uses a fixed log scale and viridis', () => {
    expect([undefined, 1e5, 1e6, 1e7, 1e9, 1e10].map(heatLevel)).toEqual([0, 0, 0.25, 0.5, 1, 1])
    expect(heatColor(0)).toBe('rgb(68, 1, 84)')
    expect(heatColor(1)).toBe('rgb(253, 231, 37)')
    expect(heatColor(0.5)).toBe('rgb(33, 145, 140)')
  })

  it('fills online seats by traffic and keeps the other shapes', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    const toggle = await screen.findByRole('switch', { name: 'Traffic' })
    expect(container.querySelector('.seat.heat')).toBeNull()
    fireEvent.click(toggle)
    await waitFor(() => expect(container.querySelector('[data-seat="D-1"] .seat')).toHaveClass('heat'))
    expect(container.querySelector('[data-seat="D-1"] .seat')).toHaveStyle({ fill: heatColor(heatLevel(6_000_000)) })
    expect(container.querySelector('[data-seat="D-2"] .slash')).not.toBeNull()
    expect(screen.getByRole('list', { name: 'Legend' })).toHaveTextContent('100 kbit/s')
  })
})

describe('Seats page', () => {
  it('draws every state with its own shape and opens the inspector', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    expect(await screen.findByRole('list', { name: 'Legend' })).toBeInTheDocument()
    const seat = (s: string) => container.querySelector(`[data-seat="${s}"]`)!
    expect(seat('D-1').querySelector('.s-online')).not.toBeNull()
    expect(seat('D-1').querySelector('.chk')).not.toBeNull()
    expect(seat('D-2').querySelector('.slash')).not.toBeNull()
    expect(seat('D-2').querySelector('.prob')).not.toBeNull()
    expect(seat('D-3').querySelector('.s-unknown')).not.toBeNull()
    expect(seat('D-4').querySelector('.match')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'D-2: Offline · 1 problem' })).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Legend' })).toHaveTextContent('Checked in')

    fireEvent.click(seat('D-2'))
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.getByText('No link')).toBeInTheDocument()
    expect(screen.getByText(/your role can't see nicks/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Show in the editor' })).toHaveAttribute('href', '/?seat=D-2')
  })

  it('dims seats a filter leaves out and finds a seat', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-4': { ...details, seat: 'D-4' } }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    fireEvent.click(await screen.findByText('Problems'))
    await waitFor(() => expect(container.querySelector('[data-seat="D-1"]')).toHaveClass('dim'))
    expect(container.querySelector('[data-seat="D-2"]')).not.toHaveClass('dim')
    const find = screen.getByRole('textbox', { name: 'Find a seat' })
    fireEvent.change(find, { target: { value: 'z9' } })
    expect(screen.getByText('No such seat here')).toBeInTheDocument()
    fireEvent.change(find, { target: { value: 'd4' } })
    fireEvent.submit(find.closest('form')!)
    await waitFor(() => expect(container.querySelector('[data-seat="D-4"]')).toHaveClass('sel'))
  })

  it('says so when there is no recent port read', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': { ...data, monitoring: false } }).fn)
    renderWithApp(<FloorPlan />, '/plan')
    expect(await screen.findByText(/No recent port read/)).toBeInTheDocument()
  })

  it('bounces the port and flags the seat for a tech', async () => {
    const tech = { enabled: true, user: { ...me.user, permissions: ['floorplan.view', 'ports.act', 'incidents.work'] } }
    const api = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details,
      'GET /api/ports': { available: true, needs_login: true, plugin: 'SSH' },
      'POST /api/ports/bounce': { ok: true, message: 'Gi1/0/2 on sw-d-01 bounced.' },
      'POST /api/incidents': { id: 'i2' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    fireEvent.click(await screen.findByRole('button', { name: 'Bounce port' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Your switch username/), { target: { value: 'tia' } })
    fireEvent.change(within(dialog).getByLabelText(/Your switch password/), { target: { value: 'secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Bounce port' }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'POST', path: '/api/ports/bounce', body: { seat: 'D-2', username: 'tia', password: 'secret' } }))
    expect(await screen.findByText('Gi1/0/2 on sw-d-01 bounced.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Flag for a tech' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'What should the tech look at?' }), { target: { value: 'No link' } })
    fireEvent.click(screen.getByRole('button', { name: 'Flag the seat' }))
    await waitFor(() => expect(api.calls).toContainEqual({ method: 'POST', path: '/api/incidents', body: { seat: 'D-2', title: 'Tech visit', note: 'No link' } }))
  })

  it('offers no actions to a viewer', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bounce port' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Flag for a tech' })).toBeNull()
  })
})
