import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventReplayData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Replay from './Replay'
import { heatmap, sampleAt } from './replay/model'

afterEach(() => vi.unstubAllGlobals())

const t0 = 1_800_000_000
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: ['floorplan.view'] } }
const cells = ['D-1', 'D-2', 'D-3'].map((seat, i) => ({ seat, x: i * 32 - 48, y: -16, hit: false, on: null }))
const drawing = { shapes: [{ cx: 400, cy: 300, rotation: 0, w: 96, h: 32, name: 'D', cells }], box: '0 0 800 600', cell: 32 }

const event: EventReplayData = {
  halls: [{ id: 'main', name: 'Hall' }], hall: 'main', step: 300,
  drawing, start: t0, end: t0 + 7200,
  frames: [
    { t: t0, down: 1e8, up: 1e7, online: 1, seats: ['D-1'], incidents: [], blocks: { D: [3, 1, 1e8, 0] } },
    { t: t0 + 3600, down: 2e9, up: 2e8, online: 3, seats: ['D-1', 'D-2', 'D-3'], incidents: ['D-2'], blocks: { D: [3, 3, 2e9, 1] } },
    { t: t0 + 7200, down: 5e8, up: 5e7, online: 2, seats: ['D-2', 'D-3'], incidents: [], blocks: { D: [3, 2, 5e8, 0] } },
  ],
}

describe('replay model', () => {
  it('finds the frame at a time', () => {
    expect(sampleAt(event.frames, t0 + 1000)?.online).toBe(1)
    expect(sampleAt(event.frames, t0 + 4000)?.online).toBe(3)
    expect(sampleAt(event.frames, t0 - 10)?.online).toBe(1)
  })
})

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

describe('Replay', () => {
  it('plays the recording on the plan', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay/event': event }).fn)
    const { container } = renderWithApp(<Replay />)
    expect(await screen.findByRole('img', { name: /Heatmap of the seat blocks/ })).toBeInTheDocument()
    expect(screen.getByText('1 / 3')).toBeInTheDocument()
    const slider = screen.getByRole('slider', { name: 'Time' })
    slider.focus()
    for (let i = 0; i < 12; i++) fireEvent.keyDown(slider, { key: 'ArrowRight' })
    expect(await screen.findByText('3 / 3')).toBeInTheDocument()
    expect(container.querySelector('.fb-replay-plan .ring')).not.toBeNull()
    expect(screen.getByRole('link', { name: 'Download JSON' })).toHaveAttribute('href', '/api/replay/event.json')
    expect(screen.queryByRole('button', { name: /video/i })).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: 'Traffic' }))
    expect(screen.getByRole('img', { name: /Traffic/ })).toBeInTheDocument()
  })

  it('explains an empty recording', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/replay/event': { ...event, frames: [], start: null, end: null } }).fn)
    renderWithApp(<Replay />)
    expect(await screen.findByText(/Floorbit writes a frame of the whole event/)).toBeInTheDocument()
  })
})
