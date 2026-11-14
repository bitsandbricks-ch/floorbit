import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReplayData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Replay from './Replay'
import { openAt, sampleAt, seatsAt } from './replay/model'

afterEach(() => vi.unstubAllGlobals())

const t0 = 1_800_000_000
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: ['floorplan.view'] } }
const cells = ['D-1', 'D-2', 'D-3'].map((seat, i) => ({ seat, x: i * 32 - 48, y: -16, hit: false, on: null }))
const data: ReplayData = {
  halls: [{ id: 'main', name: 'Hall' }], hall: 'main', interval: 120,
  drawing: { shapes: [{ cx: 400, cy: 300, rotation: 0, w: 96, h: 32, name: 'D', cells }], box: '0 0 800 600', cell: 32 },
  start: t0, end: t0 + 3600, last_poll: t0 + 3600,
  samples: [{ t: t0, down: 1e9, up: 1e8, online: 1 }, { t: t0 + 1800, down: 4e9, up: 4e8, online: 2 }],
  peak: { bps: 4.4e9, at: t0 + 1800 },
  seat_base: { t: t0, online: ['D-1'] },
  seat_events: [[t0 + 1800, 'D-2', 1], [t0 + 3000, 'D-1', 0]],
  checkins: [[t0 + 60, 'D-3', 1]],
  incidents: [{ id: 'i1', title: 'Port flapping', seat: 'D-2', switch: null, start: t0 + 1700, end: t0 + 2400 }],
}

describe('replay model', () => {
  it('folds seat changes up to a time', () => {
    expect([...seatsAt(['D-1'], data.seat_events, t0 + 10)]).toEqual(['D-1'])
    expect([...seatsAt(['D-1'], data.seat_events, t0 + 1800)].sort()).toEqual(['D-1', 'D-2'])
    expect([...seatsAt(['D-1'], data.seat_events, t0 + 3600)]).toEqual(['D-2'])
  })

  it('finds the sample and the open incidents at a time', () => {
    expect(sampleAt(data.samples, t0 + 1000)?.online).toBe(1)
    expect(sampleAt(data.samples, t0 + 2000)?.online).toBe(2)
    expect(openAt(data.incidents, t0 + 2000).map((i) => i.id)).toEqual(['i1'])
    expect(openAt(data.incidents, t0 + 2500)).toEqual([])
  })
})

describe('Replay', () => {
  it('draws the hall at the start and moves with the slider', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay': data }).fn)
    const { container } = renderWithApp(<Replay />)
    expect(await screen.findByText('1 / 3')).toBeInTheDocument()
    expect(container.querySelector('[data-seat="D-1"]')).toHaveClass('on')
    const slider = screen.getByRole('slider', { name: 'Time' })
    slider.focus()
    for (let i = 0; i < 17; i++) fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(await screen.findByText('2 / 3')).toBeInTheDocument()
    expect(screen.getByText(/Port flapping/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Checked in' }))
    expect(container.querySelector('[data-seat="D-3"]')).toHaveClass('on')
  })

  it('explains an empty history', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay': { ...data, start: null, end: null, samples: [] } }).fn)
    renderWithApp(<Replay />)
    expect(await screen.findByText(/Nothing recorded yet/)).toBeInTheDocument()
  })
})
