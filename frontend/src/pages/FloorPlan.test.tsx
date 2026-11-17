import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatDetails, SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { useLocation } from 'react-router-dom'
import FloorPlan from './FloorPlan'
import axe from 'axe-core'
import { density, findSeat, heatColor, heatLevel, linkSpans, matches, nearestSeat, seatOrder, nextSeat, parseBox, reveal, seatCenter, zoom } from './plan/model'

afterEach(() => vi.unstubAllGlobals())

const cells = ['D-1', 'D-2', 'D-3', 'D-4'].map((seat, i) => ({ x: i * 32 - 64, y: -16, hit: false, seat, on: null }))
const drawing = { shapes: [{ cx: 640, cy: 500, rotation: 0, w: 128, h: 32, name: 'D', cells }], box: '544 420 192 128', cell: 32 }
const data: SeatViewData = {
  halls: [{ id: 'main', name: 'Hall', seats: 4, online: 2, problems: 1 }], hall: 'main', drawing, size: { w: 1600, h: 1000, cell: 32 }, background: null, switches: [],
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

  it('draws the links between placed switches, a down one dashed', async () => {
    const withLinks: SeatViewData = {
      ...data,
      switches: [{ id: 's1', name: 'sw-d-01', status: 'online', x: 600, y: 300 }, { id: 's2', name: 'dist-01', status: 'online', x: 800, y: 100 }],
      links: [{ id: 'l1', a: 'sw-d-01', b: 'dist-01', type: 'fiber-mm', media: 'fiber', speed: 10, issue: 'down' }],
    }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': withLinks }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    await waitFor(() => expect(container.querySelector('line.uplink')).not.toBeNull())
    const line = container.querySelector('line.uplink')!
    expect(line).toHaveClass('m-fiber', 'down')
    expect(line.querySelector('title')?.textContent).toBe('sw-d-01 – dist-01 · 10G · Down')
  })

  it('shows the power layer: each board and a cable per circuit, a tripped one dashed (issue #468)', async () => {
    const withSwitch: SeatViewData = { ...data, switches: [{ id: 's1', name: 'sw-d-01', status: 'online', x: 600, y: 300 }] }
    const markers = {
      enabled: true, counts: { tripped: 1 },
      boards: [{ id: 'b1', name: 'DB-1', x: 5, y: 40, state: 'tripped' }],
      circuits: [{ id: 'c1', name: 'D row 1', board: 'b1', state: 'tripped', pct: null, seats: ['D-1', 'D-2'], switches: ['s1'] }],
    }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': withSwitch, 'GET /api/power/markers': markers }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    fireEvent.click(await screen.findByRole('button', { name: /Layers/ }))
    fireEvent.click(await screen.findByRole('switch', { name: 'Electrical: boards and power cables' }))
    await waitFor(() => expect(container.querySelectorAll('.power-layer line.pcable')).toHaveLength(2))     // to the seats and to the switch
    expect(container.querySelector('.power-layer line.pcable')).toHaveClass('pw-tripped')
    expect(container.querySelector('.power-layer line.pcable title')?.textContent).toBe('D row 1: Tripped')
    expect(container.querySelector('.pboard title')?.textContent).toBe('DB-1')
    expect(screen.getByText('Tripped', { selector: 'li' })).toBeInTheDocument()
  })

  it('rings the seats whose traffic failed over or has no firewall left (issue #470)', async () => {
    const seats = { enabled: true, seats: { 'D-1': { now: 'fw-02', intended: 'fw-01', state: 'failover' }, 'D-2': { now: null, intended: 'fw-01', state: 'down' } } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/firewalls/seats': seats }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    expect(container.querySelector('.cell .fwr')).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: /Layers/ }))
    fireEvent.click(await screen.findByRole('switch', { name: 'Firewall per seat' }))
    await waitFor(() => expect(container.querySelector('[data-seat="D-1"] .fwr')).toHaveClass('fw-failover'))
    expect(container.querySelector('[data-seat="D-2"] .fwr')).toHaveClass('fw-down')
    expect(screen.getByText('Seat has no firewall up', { selector: 'li' })).toBeInTheDocument()
  })

  it('keeps the firewall layer off without planned ranges', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/firewalls/seats': { enabled: false, seats: {} } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<FloorPlan />, '/plan')
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/firewalls/seats')).toBe(true))
    fireEvent.click(await screen.findByRole('button', { name: /Layers/ }))
    await screen.findByRole('switch', { name: 'Status: traffic per seat' })
    // Listed, so the layer is known, but off until ranges are planned.
    await waitFor(() => expect(screen.getByRole('switch', { name: /^Firewall per seat/, hidden: true })).toBeDisabled())
  })

  it('fills online seats by traffic and keeps the other shapes', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    fireEvent.click(await screen.findByRole('button', { name: /Layers/ }))
    const toggle = await screen.findByRole('switch', { name: 'Status: traffic per seat' })
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
    expect(document.title).toBe('(1) Floor plan · Floorbit')   // D-2 has a problem: shows in a background tab

    fireEvent.click(seat('D-2'))
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.getByText('No link')).toBeInTheDocument()
    expect(screen.getByText(/your role can't see nicks/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Show in the editor' })).toHaveAttribute('href', '/?seat=D-2')
    expect(screen.getByRole('img', { name: /^Offline since .+\. 3 changes in 6 h$/ })).toBeInTheDocument()
  })

  it('says what was fixed at the seat before and links its incidents (issue #330)', async () => {
    const again = { ...details, fixed_before: { count: 2, last: { title: 'Cable loose', fixed_at: 1_799_990_000 } } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': again }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    await screen.findByRole('list', { name: 'Legend' })
    fireEvent.click(container.querySelector('[data-seat="D-2"]')!)
    expect(await screen.findByText(/^Fixed here 2 times before, last: Cable loose \(/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Incidents' })).toHaveAttribute('href', '/incidents?q=seat%3AD-2')
    expect(screen.queryByRole('link', { name: 'QR code' })).toBeNull()      // printing codes needs incidents.assign
  })

  it('says which firewall the seat takes now when its range failed over (issue #470)', async () => {
    const moved = { ...details, firewall: { intended: 'fw-03', now: 'fw-04', state: 'failover', range: 'Seats C' } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': moved }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    await screen.findByRole('list', { name: 'Legend' })
    fireEvent.click(container.querySelector('[data-seat="D-2"]')!)
    expect(await screen.findByText('fw-04 (failed over from fw-03)')).toBeInTheDocument()
  })

  it('links a lead to the seat\'s and the block\'s QR codes (issue #380)', async () => {
    const lead = { enabled: true, user: { ...me.user, role: 'lead', permissions: ['floorplan.view', 'incidents.work', 'incidents.assign'] } }
    const block = { name: 'D', hall: 'main', seats: 4, online: 2, offline: 1, unknown: 1, checked_in: 1, bps: null, problems: [], switches: [], no_port: 0 }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details, 'GET /api/plan/blocks/D': block }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByRole('link', { name: 'QR code' })).toHaveAttribute('href', '/incidents/qr?seats=D-2')
    fireEvent.click(screen.getByRole('button', { name: 'Open block D' }))
    expect(await screen.findByRole('link', { name: 'Print QR codes' })).toHaveAttribute('href', '/incidents/qr?block=D')
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
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details }).fn)
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
      const two = [{ ...data.halls[0] }, { id: 'annex', name: 'Annex', seats: 0, online: 0, problems: 0 }]
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

  it('shows the time, blocks with problems and other halls\' problems on a big screen', async () => {
    const two = [...data.halls, { id: 'annex', name: 'Annex', seats: 2, online: 0, problems: 2 }]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': { ...data, halls: two } }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?screen=1')
    const blocks = await screen.findByLabelText('Blocks with problems')
    expect(within(blocks).getByText('D: 1 seat')).toBeInTheDocument()
    expect(screen.getByText('2 seats with problems in other halls')).toBeInTheDocument()
    expect(container.querySelector('.fb-screen-clock')?.textContent).toMatch(/^\d\d:\d\d$/)
  })

  it('counts seats with problems by each block\'s name, and marks a block where many have them', async () => {
    const bad = { ...data, blocks: [{ name: 'D', seats: 4, online: 1, problems: 2 }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': bad }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    await waitFor(() => expect(container.querySelector('.fb-plan .name-bad')?.textContent).toBe('! 2'))
    expect(container.querySelector('.fb-plan .blk.alarm')).not.toBeNull()
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
    const show = within(screen.getByRole('radiogroup', { name: 'Show' }))
    expect(show.getByText('Offline').parentElement).toHaveTextContent('Offline 1')
    expect(show.getByText('Problems').parentElement).toHaveTextContent('Problems 1')
    fireEvent.click(show.getByText('Offline'))
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
      'GET /api/auth/me': tech, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details,
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
      vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details }).fn)
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
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bounce port' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Flag for a tech' })).toBeNull()
  })

  it('lets the crew leave a note on a seat', async () => {
    const noted = { ...data, seats: { ...data.seats, 'D-2': { ...data.seats['D-2'], note: true } } }
    const note = { text: 'Cable swapped at 14:20', by: 'Tia', at: 1_800_000_000 }
    const api = fakeFetch({
      'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': noted, 'GET /api/plan/seats/D-2': { ...details, crew: true, note },
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
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': details }).fn)
    renderWithApp(<FloorPlan />, '/plan?seat=D-2')
    expect(await screen.findByText('sw-d-01 · Gi1/0/2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add a note' })).toBeNull()
  })

  it('shows the seat speed tests to the crew, marking ones from before the last link change', async () => {
    const speedtests = [
      { down_mbps: 480, up_mbps: 120, ping_ms: 4, at: 1_799_999_000 },
      { down_mbps: 12, up_mbps: 3, ping_ms: 40, at: 1_799_994_000 },
    ]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?seat=D-2': data, 'GET /api/plan/seats/D-2': { ...details, crew: true, speedtests } }).fn)
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

  it('finds players by nick for seats.view and jumps to their seat', async () => {
    const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'seats.view'] } }
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/plan': data, 'GET /api/plan/seats/D-2': details, 'GET /api/plan/seats/D-3': { ...details, seat: 'D-3' },
      'GET /api/plan/find?q=sam': { results: [{ seat: 'D-2', nick: 'sam', matched: 'nick', hall: 'main' }, { seat: 'D-3', nick: 'samira', matched: 'nick', hall: 'main' }] },
      'GET /api/plan/find?q=sami': { results: [{ seat: 'D-3', nick: 'samira', matched: 'nick', hall: 'main' }] },
      'GET /api/plan/find?q=zz': { results: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<FloorPlan />, '/plan')
    const box = await screen.findByRole('textbox', { name: 'Find a seat' })
    await waitFor(() => expect(box).toHaveAttribute('placeholder', 'Seat, nick, block or switch'))
    fireEvent.change(box, { target: { value: 'sam' } })
    fireEvent.submit(box.closest('form')!)
    const list = await screen.findByRole('list', { name: 'Players found' })
    fireEvent.click(within(list).getByRole('button', { name: 'samira · D-3' }))
    expect(await screen.findByRole('heading', { name: 'Seat D-3' })).toBeInTheDocument()

    fireEvent.change(box, { target: { value: 'zz' } })
    fireEvent.submit(box.closest('form')!)
    expect(await screen.findByText('No seat or player found')).toBeInTheDocument()
  })

  it('keeps the seat-only search without seats.view', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<FloorPlan />, '/plan')
    const box = await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.change(box, { target: { value: 'sam' } })
    fireEvent.submit(box.closest('form')!)
    expect(await screen.findByText('No such seat here')).toBeInTheDocument()
    expect(api.calls.some((c) => c.path.startsWith('/api/plan/find'))).toBe(false)
  })

  it('prints the whole hall with every seat numbered, keeping the filter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data }).fn)
    const printed = vi.fn()
    vi.stubGlobal('print', printed)
    const { container } = renderWithApp(<FloorPlan />, '/plan?print=1&hall=main&show=offline')
    expect(await screen.findByText('Seats: Hall')).toBeInTheDocument()
    expect(screen.getByText('Only: Offline')).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('light')
    // Close-up detail on paper: seat numbers, whatever the size.
    expect(container.querySelector('.fb-plan-wrap')).toHaveClass('d-near')
    fireEvent.click(screen.getByRole('button', { name: 'Print' }))
    expect(printed).toHaveBeenCalled()
  })

  it('links to the print sheet with the current filter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    renderWithApp(<FloorPlan />, '/plan')
    const link = await screen.findByRole('link', { name: 'Print' })
    expect(link).toHaveAttribute('href', '/plan?print=1&hall=main')
    fireEvent.click(within(screen.getByRole('radiogroup', { name: 'Show' })).getByText('Offline'))
    await waitFor(() => expect(link).toHaveAttribute('href', '/plan?print=1&hall=main&show=offline'))
  })

  it('puts the cursor in Find on /', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    renderWithApp(<FloorPlan />, '/plan')
    const box = await screen.findByRole('textbox', { name: 'Find a seat' })
    expect(box).toHaveAttribute('aria-keyshortcuts', '/')
    fireEvent.change(box, { target: { value: 'D-2' } })
    box.blur()
    fireEvent.keyDown(document.documentElement, { key: '/', code: 'Slash' })
    expect(box).toHaveFocus()
    const input = box as HTMLInputElement
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, 3])
    // Swiss German and German keyboards: Shift+7 types "/" (issue #222).
    box.blur()
    fireEvent.keyDown(document.documentElement, { key: '/', code: 'Digit7', shiftKey: true })
    expect(box).toHaveFocus()
  })

  it('lists the keyboard shortcuts on ? (issue #224)', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    renderWithApp(<FloorPlan />, '/plan')
    await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.keyDown(document.documentElement, { key: '?', code: 'Slash', shiftKey: true })
    const dialog = await screen.findByRole('dialog', { name: 'Keyboard shortcuts' })
    expect(within(dialog).getByText('Open the block of the seat under the cursor')).toBeInTheDocument()
    expect(within(dialog).getByText('Find a seat')).toBeInTheDocument()
  })

  it('shows every hall with its totals in the picker', async () => {
    const halls = [data.halls[0], { id: 'annex', name: 'Annex', seats: 40, online: 38, problems: 2 }]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': { ...data, halls } }).fn)
    renderWithApp(<FloorPlan />, '/plan?hall=main')
    expect(await screen.findByText('2 seats with problems in other halls')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Hall', { selector: 'input' }))
    // The dropdown is still fading in under jsdom, so look the options up by their text.
    const option = async (name: string) => (await screen.findByText(name, { selector: 'p' })).closest('[role=option]')
    expect(await option('Annex')).toHaveTextContent('Annex38/40 online · 2 with problems')
    expect(await option('Hall')).toHaveTextContent('Hall2/4 online · 1 with problems')
  })

  it('copies a link to the open seat', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data, 'GET /api/plan/seats/D-2': details }).fn)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithApp(<FloorPlan />, '/plan?hall=main&show=offline&seat=D-2')
    fireEvent.click(await screen.findByRole('button', { name: 'Copy link' }))
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/plan?hall=main&show=offline&seat=D-2`)
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('finds a block or a switch by its name and opens its panel', async () => {
    const withSwitch = { ...data, switches: [{ id: 's1', name: 'sw-d-01', status: 'up', x: 640, y: 420 }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': withSwitch }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan')
    const find = await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.change(find, { target: { value: 'd' } })
    expect(screen.queryByText('No such seat here')).toBeNull()
    fireEvent.submit(find.closest('form')!)
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('block=D'))
    fireEvent.change(find, { target: { value: 'sw-d' } })
    fireEvent.submit(find.closest('form')!)
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('switch=sw-d-01'))
    expect(screen.getByLabelText('address')).not.toHaveTextContent('block=')
  })

  it('shows an overview of the hall once zoomed in, and a click on it moves the plan there', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan')
    const map = await screen.findByRole('application', { name: 'Seat map' })
    expect(screen.queryByRole('img', { name: /Overview of the hall/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    const mini = await screen.findByRole('img', { name: /Overview of the hall/ })
    expect(container.querySelectorAll('.fb-minimap .blk')).toHaveLength(1)
    mini.getBoundingClientRect = () => ({ left: 0, top: 0, width: 192, height: 128, right: 192, bottom: 128, x: 0, y: 0, toJSON: () => ({}) })
    const before = map.getAttribute('viewBox')
    fireEvent.pointerDown(mini, { pointerId: 1, clientX: 0, clientY: 0 })
    expect(map.getAttribute('viewBox')).not.toBe(before)
    const [x, y, w, h] = map.getAttribute('viewBox')!.split(' ').map(Number)
    expect(x + w / 2).toBeCloseTo(544)   // the drawing box's left edge
    expect(y + h / 2).toBeCloseTo(420)
  })

  it('lights up the seats of the switch whose panel is open', async () => {
    const withSwitch = { ...data, switches: [{ id: 's1', name: 'sw-d-01', status: 'online', x: 640, y: 420 }] }
    const sw = { name: 'sw-d-01', status: 'online', since: null, model: null, online: 1,
      seats: [{ seat: 'D-1', port: 'Gi1/0/1', state: 'online', problems: 0 }, { seat: 'D-2', port: 'Gi1/0/2', state: 'offline', problems: 1 }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': withSwitch, 'GET /api/plan/switches/sw-d-01': sw }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?hall=main&switch=sw-d-01')
    await waitFor(() => expect(container.querySelector('[data-seat="D-3"]')).toHaveClass('dim'))
    expect(container.querySelector('[data-seat="D-1"]')).not.toHaveClass('dim')
    expect(container.querySelector('[data-seat="D-2"]')).not.toHaveClass('dim')
    expect(container.querySelector('[data-seat="D-4"]')).toHaveClass('dim')
    expect(container.querySelector('.sw-focus')).not.toBeNull()
  })

  it('rings an open seat\'s switch and draws the way there, dimming nothing', async () => {
    const withSwitch = { ...data, switches: [{ id: 's1', name: 'sw-d-01', status: 'online', x: 640, y: 420 }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': withSwitch, 'GET /api/plan/seats/D-2': details }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?hall=main&seat=D-2')
    await waitFor(() => expect(container.querySelector('.sw-trace')).not.toBeNull())
    const line = container.querySelector('.sw-trace')!
    expect([line.getAttribute('x2'), line.getAttribute('y2')]).toEqual(['640', '420'])
    expect(container.querySelector('.sw-focus')).not.toBeNull()
    expect(container.querySelector('.cell.dim')).toBeNull()
  })

  it('closes the open panel with Esc, and Esc in the search box only clears it', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data, 'GET /api/plan/seats/D-2': details }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan?hall=main&seat=D-2')
    const find = await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.change(find, { target: { value: 'z9' } })
    fireEvent.keyDown(find, { key: 'Escape' })
    expect(find).toHaveValue('')
    expect(screen.getByLabelText('address')).toHaveTextContent('seat=D-2')
    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent(/^\?hall=main$/))
  })

  it('filters to the seats with problems from the Problems chip in the top bar, and back', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data, 'GET /api/plan?hall=main&show=problems': data }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan?hall=main')
    const show = within(await screen.findByRole('radiogroup', { name: 'Show' }))
    // The chip carries the count, so it is the summary too (the separate "1 with problems" link is gone).
    expect(show.getByText('Problems').parentElement).toHaveTextContent('Problems 1')
    expect(screen.queryByRole('button', { name: '1 with problems' })).toBeNull()
    fireEvent.click(show.getByText('Problems'))
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('show=problems'))
    fireEvent.click(show.getByText('All'))
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent(/^\?hall=main$/))
  })

  it('fills the page like a map editor: no reading width, the legend floats over the plan and folds', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data }).fn)
    renderWithApp(<FloorPlan />, '/plan?hall=main')
    await screen.findByRole('application', { name: 'Seat map' })
    expect(screen.getByRole('main')).toHaveClass('fb-main-full')
    const key = screen.getByRole('region', { name: 'Legend' })
    const fold = within(key).getByRole('button', { name: 'Legend' })
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(fold)
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list', { name: 'Legend' })).toBeNull()
    // The how-to moved from under the map into the shortcuts dialog.
    fireEvent.click(screen.getByRole('button', { name: 'Keyboard shortcuts' }))
    expect(await screen.findByText(/^Drag to move, scroll or pinch to zoom/)).toBeInTheDocument()
  })

  it('switches between the map and the list with L', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data, 'GET /api/plan?hall=main&view=list': data }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan?hall=main')
    await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.keyDown(document.body, { key: 'l' })
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('view=list'))
    fireEvent.keyDown(document.body, { key: 'l' })
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent(/^\?hall=main$/))
    // Not while the shortcut list is open.
    fireEvent.keyDown(document.body, { key: '?' })
    await screen.findByRole('dialog')
    fireEvent.keyDown(document.body, { key: 'l' })
    fireEvent.keyDown(document.body, { key: '2' })
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByLabelText('address')).toHaveTextContent(/^\?hall=main$/)
  })

  it('switches the layer preset with 1 to 4, but not while typing', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': data }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan?hall=main')
    const find = await screen.findByRole('textbox', { name: 'Find a seat' })
    fireEvent.keyDown(document.body, { key: '2' })
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('layers=grid%2Cmarks%2Cnetwork%2Cwifi'))
    fireEvent.keyDown(document.body, { key: '3' })
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('layers=grid%2Cmarks%2Celectrical'))
    fireEvent.keyDown(find, { key: '1' })
    expect(screen.getByLabelText('address')).toHaveTextContent('electrical')
  })

  it('keeps only the open block bright', async () => {
    const two = { ...drawing, shapes: [...drawing.shapes, { cx: 640, cy: 700, rotation: 0, w: 32, h: 32, name: 'E', cells: [{ x: -16, y: -16, hit: false, seat: 'E-1', on: null }] }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan?hall=main': { ...data, drawing: two, seats: { ...data.seats, 'E-1': { state: 'online' } } } }).fn)
    const { container } = renderWithApp(<FloorPlan />, '/plan?hall=main&block=E')
    await waitFor(() => expect(container.querySelector('[data-seat="D-1"]')).toHaveClass('dim'))
    expect(container.querySelector('[data-seat="E-1"]')).not.toHaveClass('dim')
    expect(container.querySelector('.sw-focus')).toBeNull()
  })

  it('keeps the filter in the address', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/plan': data, 'GET /api/plan?hall=main': data }).fn)
    function Where() { return <output aria-label="address">{useLocation().search}</output> }
    renderWithApp(<><FloorPlan /><Where /></>, '/plan?hall=main&show=offline')
    const show = within(await screen.findByRole('radiogroup', { name: 'Show' }))
    expect(show.getByRole('radio', { name: /^Offline/ })).toBeChecked()
    fireEvent.click(show.getByText('All'))
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent(/^\?hall=main$/))
    fireEvent.click(show.getByText('Problems'))
    await waitFor(() => expect(screen.getByLabelText('address')).toHaveTextContent('?hall=main&show=problems'))
  })
})
