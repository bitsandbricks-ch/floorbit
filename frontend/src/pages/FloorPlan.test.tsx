import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatDetails, SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import FloorPlan from './FloorPlan'
import axe from 'axe-core'
import { density, findSeat, heatColor, heatLevel, linkSpans, matches, nearestSeat, seatOrder, nextSeat, parseBox, reveal, seatCenter, zoom } from './plan/model'

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
  match: null, checked_in: false, last_read: 1_800_000_000, people: false, crew: false,
  history: { from: 1_800_000_000 - 6 * 3600, to: 1_800_000_000, start: true, changes: [[1_799_990_000, 0], [1_799_991_000, 1], [1_799_995_000, 0]] },
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
    expect(['D-10', 'A-3', 'D-2', 'A-12'].sort(seatOrder)).toEqual(['A-3', 'A-12', 'D-2', 'D-10'])
    expect(matches(data.seats['D-2'], 'problems') && !matches(data.seats['D-1'], 'offline')).toBe(true)
  })
})

describe('keyboard', () => {
  it('moves from seat to seat by where seats are, in rotated blocks too', () => {
    expect(nextSeat(drawing, 'D-1', 'right')).toBe('D-2')
    expect(nextSeat(drawing, 'D-4', 'right')).toBeNull()
    expect(nextSeat(drawing, 'D-2', 'up')).toBeNull()
    const upright = { ...drawing, shapes: [{ ...drawing.shapes[0], rotation: 90 }] }
    expect(nextSeat(upright, 'D-1', 'down')).toBe('D-2')
    expect(nextSeat(upright, 'D-1', 'right')).toBeNull()
    expect(nearestSeat(drawing, { x: 700, y: 480 })).toBe('D-4')
  })

  it('keeps the view until the seat nears its edge, then centres it', () => {
    const view = parseBox('0 0 400 200')
    expect(reveal(view, { x: 200, y: 100 }, 64)).toBe(view)
    expect(reveal(view, { x: 380, y: 100 }, 64)).toEqual({ x: 180, y: 0, w: 400, h: 200 })
  })
})

describe('link history', () => {
  it('turns changes into spans, not-known-yet included', () => {
    expect(linkSpans({ from: 0, to: 100, start: true, changes: [[40, 0], [70, 1]] })).toEqual([
      { from: 0, to: 40, on: true }, { from: 40, to: 70, on: false }, { from: 70, to: 100, on: true }])
    expect(linkSpans({ from: 0, to: 100, start: null, changes: [[30, 1]] })).toEqual([
      { from: 0, to: 30, on: null }, { from: 30, to: 100, on: true }])
    expect(linkSpans({ from: 0, to: 100, start: false, changes: [] })).toEqual([{ from: 0, to: 100, on: false }])
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
    expect(screen.getByRole('img', { name: /^Offline since .+\. 3 changes in 6 h$/ })).toBeInTheDocument()
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

  it('goes from seat to seat with the keyboard and opens one with Enter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    const map = await screen.findByRole('application', { name: 'Seat map' })
    expect(map).toHaveAccessibleDescription(/Arrow keys move from seat to seat.*Block D: 2 of 4 seats online, 1 problem\./)
    map.focus()
    fireEvent.keyDown(map, { key: 'ArrowRight' })   // the first press starts on the seat in the middle
    const cursor = () => container.querySelector('.cell.kb')?.getAttribute('data-seat')
    expect(cursor()).toBe('D-2')
    expect(map.getAttribute('aria-activedescendant')).toBe(container.querySelector('[data-seat="D-2"]')!.id)
    expect(screen.getByRole('status')).toHaveTextContent('D-2: Offline · 1 problem')
    fireEvent.keyDown(map, { key: 'ArrowRight' })
    fireEvent.keyDown(map, { key: 'ArrowLeft' })
    expect(cursor()).toBe('D-2')
    fireEvent.keyDown(map, { key: 'Enter' })
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    fireEvent.keyDown(map, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByText('sw-d-01 · Gi1/0/2')).toBeNull())
  })

  it('passes an axe check', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    // jsdom does no layout, so colour contrast is checked in the browser, not here.
    const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(result.passes.length).toBeGreaterThan(10)
    expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([])
  })

  it('rotates through the halls on a big screen, longer where there are problems', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const two = [{ id: 'main', name: 'Hall' }, { id: 'annex', name: 'Annex' }]
      const quiet = Object.fromEntries(Object.keys(data.seats).map((k) => [k, { state: 'online' as const }]))
      const api = fakeFetch({
        'GET /api/plan?hall=main': { ...data, halls: two },
        'GET /api/plan?hall=annex': { ...data, halls: two, hall: 'annex', seats: quiet },
      })
      vi.stubGlobal('fetch', api.fn)
      const { container } = renderWithApp(<FloorPlan />, '/plan?screen=1&cycle=10&hall=main')
      expect(await screen.findByText('Hall')).toBeInTheDocument()
      expect(container.querySelector('.fb-plan-cycle')).toHaveStyle({ animationDuration: '20000ms' })   // Hall has a problem
      await vi.advanceTimersByTimeAsync(19_000)
      expect(api.calls.some((c) => c.path === '/api/plan?hall=annex')).toBe(false)
      await vi.advanceTimersByTimeAsync(1_500)
      expect(await screen.findByText('Annex')).toBeInTheDocument()
      expect(container.querySelector('.fb-plan-cycle')).toHaveStyle({ animationDuration: '10000ms' })
      await vi.advanceTimersByTimeAsync(10_500)
      await waitFor(() => expect(screen.getByText('Hall')).toBeInTheDocument())
    } finally {
      vi.useRealTimers()
    }
  })

  it('lists the seats in a sortable table that follows the filter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?view=list')
    const table = await screen.findByRole('table', { name: 'Seats' })
    const seats = () => within(table).getAllByRole('row').slice(1).map((r) => r.querySelector('td')!.textContent)
    expect(seats()).toEqual(['D-1', 'D-2', 'D-3', 'D-4'])
    expect(container.querySelector('svg[role=application]')).toBeNull()
    fireEvent.click(within(table).getByRole('button', { name: 'State' }))
    expect(seats()).toEqual(['D-2', 'D-3', 'D-1', 'D-4'])
    expect(within(table).getByRole('columnheader', { name: 'State' })).toHaveAttribute('aria-sort', 'ascending')
    fireEvent.click(within(table).getByRole('button', { name: 'Traffic' }))
    expect(seats()[0]).toBe('D-1')
    fireEvent.click(within(screen.getByRole('radiogroup', { name: 'Show' })).getByText('Offline'))
    await waitFor(() => expect(seats()).toEqual(['D-2']))
    expect(screen.getByText('1 seat')).toBeInTheDocument()

    const created: Blob[] = []
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: (b: Blob) => { created.push(b); return 'blob:x' }, revokeObjectURL: () => {} }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    fireEvent.click(screen.getByRole('button', { name: 'CSV' }))
    expect(await created[0].text()).toBe('seat,state,problems,bps,checked_in,match,note\nD-2,offline,1,,no,,no\n')
    click.mockRestore()

    fireEvent.click(within(table).getByRole('button', { name: 'D-2' }))
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(result.violations.map((v) => v.id)).toEqual([])
  })

  it('marks seats whose link changed lately and filters to them', async () => {
    const recent = { ...data, seats: { ...data.seats, 'D-3': { state: 'offline' as const, changed: Date.now() / 1000 - 240 } } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': recent }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    expect(await screen.findByRole('button', { name: 'D-3: Offline · changed 4 min ago' })).toBeInTheDocument()
    expect(container.querySelectorAll('.cell .recent')).toHaveLength(1)
    expect(screen.getByRole('list', { name: 'Legend' })).toHaveTextContent('Link changed in the last 15 minutes')
    fireEvent.click(within(screen.getByRole('radiogroup', { name: 'Show' })).getByText('Changed lately'))
    await waitFor(() => expect(container.querySelector('[data-seat="D-1"]')).toHaveClass('dim'))
    expect(container.querySelector('[data-seat="D-3"]')).not.toHaveClass('dim')
  })

  it('opens a block panel from the block name, the inspector and the B key', async () => {
    const block = {
      name: 'D', hall: 'main', seats: 4, online: 2, offline: 1, unknown: 1, checked_in: 1, bps: 6_000_000,
      problems: [{ seat: 'D-2', state: 'offline', problems: 1 }],
      switches: [{ name: 'sw-d-01', seats: 3, online: 2, status: 'online' }], no_port: 1,
    }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/blocks/D': block, 'GET /api/plan/seats/D-2': details }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    await screen.findByRole('application', { name: 'Seat map' })
    fireEvent.click(container.querySelector('text.name.link')!)
    expect(await screen.findByRole('heading', { name: 'Block D' })).toBeInTheDocument()
    expect(await screen.findByText('2 of 3 seats online')).toBeInTheDocument()
    expect(screen.getByText('1 seat on no known port')).toBeInTheDocument()
    fireEvent.click(screen.getByText('D-2 · 1'))
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Block D' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open block D' }))
    expect(await screen.findByRole('heading', { name: 'Block D' })).toBeInTheDocument()
    const map = screen.getByRole('application', { name: 'Seat map' })
    fireEvent.keyDown(map, { key: 'ArrowRight' })
    fireEvent.keyDown(map, { key: 'Enter' })
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    fireEvent.keyDown(map, { key: 'b' })
    expect(await screen.findByRole('heading', { name: 'Block D' })).toBeInTheDocument()
  })

  it('opens a switch panel from its marker and from the block panel', async () => {
    const withSwitch = { ...data, switches: [{ id: 's1', name: 'sw-d-01', status: 'offline', x: 600, y: 440 }] }
    const sw = { name: 'sw-d-01', status: 'offline', since: 1_800_000_000, model: null, online: 1,
      seats: [{ seat: 'D-1', port: 'Gi1/0/1', state: 'online', problems: 0 }, { seat: 'D-2', port: 'Gi1/0/2', state: 'offline', problems: 1 }] }
    const block = { name: 'D', hall: 'main', seats: 4, online: 2, offline: 1, unknown: 1, checked_in: 1, bps: 0, problems: [],
      switches: [{ name: 'sw-d-01', seats: 2, online: 1, status: 'offline' }], no_port: 2 }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me, 'GET /api/plan': withSwitch, 'GET /api/plan/switches/sw-d-01': sw,
      'GET /api/plan/blocks/D': block, 'GET /api/plan/seats/D-2': details,
    }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?block=D')
    fireEvent.click(await screen.findByRole('button', { name: 'sw-d-01' }))
    const seats = await screen.findByRole('table', { name: 'Seats on this switch' })
    expect(within(seats).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual(['Gi1/0/1D-1Online', 'Gi1/0/2D-2!Offline'])
    fireEvent.click(within(seats).getByRole('button', { name: 'D-2' }))
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    fireEvent.click(container.querySelector('g.sw.link')!)
    expect(await screen.findByRole('table', { name: 'Seats on this switch' })).toBeInTheDocument()
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

  it('watches a seat through notify.js', async () => {
    let prefs = { on: false, incidents: true, jobs: true, switches: true, watch: [] as string[] }
    const set = vi.fn(async (c: object) => (prefs = { ...prefs, ...c }))
    window.floorNotify = { supported: () => true, permission: () => 'granted', set, settings: () => prefs }
    try {
      vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
      renderWithApp(<FloorPlan />, '/plan?seat=D-2')
      fireEvent.click(await screen.findByRole('button', { name: 'Watch this seat' }))
      await waitFor(() => expect(set).toHaveBeenCalledWith({ watch: ['D-2'], on: true }))
      expect(await screen.findByRole('button', { name: 'Stop watching' })).toHaveAttribute('aria-pressed', 'true')
      fireEvent.click(screen.getByRole('button', { name: 'Stop watching' }))
      await waitFor(() => expect(set).toHaveBeenLastCalledWith({ watch: [] }))
    } finally {
      delete window.floorNotify
    }
  })

  it('offers no actions to a viewer', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bounce port' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Flag for a tech' })).toBeNull()
  })

  it('lets the crew leave a note on a seat', async () => {
    const noted = { ...data, seats: { ...data.seats, 'D-2': { ...data.seats['D-2'], note: true } } }
    const note = { text: 'Cable swapped at 14:20', by: 'Tia', at: 1_800_000_000 }
    const api = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/plan': noted, 'GET /api/plan/seats/D-2': { ...details, crew: true, note },
      'PUT /api/plan/seats/D-2/note': { note: null },
    })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('Cable swapped at 14:20')).toBeInTheDocument()
    expect(container.querySelector('[data-seat="D-2"] .note')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Crew note/ }), { target: { value: 'Own switch, leave it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ text: 'Own switch, leave it' }))
  })

  it('shows no note box without incidents.work', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add a note' })).toBeNull()
  })

  it('shows the seat speed tests to the crew, marking ones from before the last link change', async () => {
    const speedtests = [
      { down_mbps: 480, up_mbps: 120, ping_ms: 4, at: 1_799_999_000 },
      { down_mbps: 12, up_mbps: 3, ping_ms: 40, at: 1_799_994_000 },
    ]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': { ...details, crew: true, speedtests } }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('480')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Ping (ms)' })).toBeInTheDocument()
    expect(screen.getAllByText(/before the last link change/)).toHaveLength(1)
  })

  it('lists which seats have a crew note and sorts them first', async () => {
    const noted = { ...data, seats: { ...data.seats, 'D-3': { ...data.seats['D-3'], note: true } } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': noted }).fn)
    renderWithApp(<FloorPlan />, '/plan?view=list')
    const table = await screen.findByRole('table', { name: 'Seats' })
    fireEvent.click(within(table).getByRole('button', { name: 'Note' }))
    const first = within(table).getAllByRole('row')[1]
    expect(within(first).getByRole('button', { name: 'D-3' })).toBeInTheDocument()
    expect(within(first).getByText('Yes')).toBeInTheDocument()
  })
})
