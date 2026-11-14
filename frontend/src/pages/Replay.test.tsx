import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventReplayData, ReplayData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Replay from './Replay'
import { heatmap, openAt, sampleAt, seatsAt } from './replay/model'

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

const event: EventReplayData = {
  halls: [{ id: 'main', name: 'Hall' }], hall: 'main', step: 300,
  drawing: data.drawing, start: t0, end: t0 + 7200,
  frames: [
    { t: t0, down: 1e8, up: 1e7, online: 1, seats: ['D-1'], incidents: [], blocks: { D: [3, 1, 1e8, 0] } },
    { t: t0 + 3600, down: 2e9, up: 2e8, online: 3, seats: ['D-1', 'D-2', 'D-3'], incidents: ['D-2'], blocks: { D: [3, 3, 2e9, 1] } },
    { t: t0 + 7200, down: 5e8, up: 5e7, online: 2, seats: ['D-2', 'D-3'], incidents: [], blocks: { D: [3, 2, 5e8, 0] } },
  ],
}

describe('whole-event heatmap', () => {
  it('scales each metric to 0..1 and merges frames into at most maxCols columns', () => {
    expect(heatmap(event.frames, 'online').cols.map((c) => c.values[0])).toEqual([1 / 3, 1, 2 / 3])
    expect(heatmap(event.frames, 'traffic').cols.map((c) => c.values[0])).toEqual([0.05, 1, 0.25])
    expect(heatmap(event.frames, 'incidents').cols.map((c) => c.values[0])).toEqual([0, 1, 0])
    const merged = heatmap(event.frames, 'incidents', 2)
    expect(merged.cols).toHaveLength(2)
    expect(merged.cols[0].raw).toEqual([1])
    expect(merged.names).toEqual(['D'])
  })
})

describe('Replay, whole event', () => {
  it('switches to the recording and plays it on the plan', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay': data, 'GET /api/replay/event': event }).fn)
    const { container } = renderWithApp(<Replay />)
    await screen.findByText('1 / 3')
    fireEvent.click(screen.getByRole('radio', { name: 'Whole event' }))
    expect(await screen.findByRole('img', { name: /Heatmap of the seat blocks/ })).toBeInTheDocument()
    expect(screen.getByText('1 / 3')).toBeInTheDocument()
    const slider = screen.getByRole('slider', { name: 'Time' })
    slider.focus()
    for (let i = 0; i < 12; i++) fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(await screen.findByText('3 / 3')).toBeInTheDocument()
    expect(container.querySelector('.fb-replay-plan .ring')).not.toBeNull()
    expect(screen.getByRole('link', { name: 'Download JSON' })).toHaveAttribute('href', '/api/replay/event.json')
    fireEvent.click(screen.getByRole('radio', { name: 'Traffic' }))
    expect(screen.getByRole('img', { name: /Traffic/ })).toBeInTheDocument()
  })

  it('explains an empty recording', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay': data, 'GET /api/replay/event': { ...event, frames: [], start: null, end: null } }).fn)
    renderWithApp(<Replay />)
    await screen.findByText('1 / 3')
    fireEvent.click(screen.getByRole('radio', { name: 'Whole event' }))
    expect(await screen.findByText(/Floorbit writes a frame of the whole event/)).toBeInTheDocument()
  })
})
