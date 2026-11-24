import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { LayerState } from '../layers'
import type { View } from '../model'
import { PlanEditor } from './PlanEditor'
import { twoRows } from './rowGaps.fixtures'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

// Block A: two rows of three seats with a seat of space between them, its middle at 400,500.
const shape = { ...twoRows, id: 'A', cx: 400, cy: 500 }
const data = {
  halls: [{ id: 'main', name: 'Hall', seats: 0, online: 0, problems: 0 }], hall: 'main', seats: {}, blocks: [], switches: [],
  size: { w: 1600, h: 1000, cell: 32 }, background: null,
  drawing: { shapes: [shape], marks: [], box: '0 0 1600 1000', cell: 32 },
} as unknown as SeatViewData
const row = (id: string, gap: number) => ({ id, seats: 3, shape: 'line', gap, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [] })
const stored = { id: 'A', name: 'A', x: 25, y: 50, rotation: 0, hall_id: 'main', rows: [row('1', 0), row('2', 1)] }

function editor() {
  // The plan fills a 1600 × 1000 screen, so screen points are drawing units.
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 1600, bottom: 1000, width: 1600, height: 1000, toJSON: () => ({}) })
  const api = fakeFetch({
    'GET /api/plan-groups?hall=main': { groups: [] },
    'GET /api/power/markers': { enabled: false, boards: [], feeds: [] },
    'GET /api/cable-plan?hall=main': { cables: [], panels: [] },
    'GET /api/seat-blocks?hall=main': [stored],
    'PUT /api/seat-blocks/A': { ok: true },
  })
  vi.stubGlobal('fetch', api.fn)
  const view: View = { x: 0, y: 0, w: 1600, h: 1000 }
  const r = renderWithApp(
    <PlanEditor data={data} view={view} setView={() => {}} layers={{ on: new Set(), fade: {} } as LayerState} refresh={() => Promise.resolve()} onHall={() => {}} onShortcuts={() => {}} />,
  )
  return { ...r, api, hit: r.container.querySelector('[data-item="block:A"]')! }
}

describe('Rows on the plan', () => {
  it('picks the row under a double click in the panel', async () => {
    const e = editor()
    fireEvent.doubleClick(e.hit, { clientX: 370, clientY: 532 })
    expect(await screen.findByText('Row 2')).toBeInTheDocument()
    expect(e.container.querySelector('.fb-row-picked')).toHaveAttribute('data-picked-row', '1')
  })

  it('drags the space above a row and keeps the rows above in place', async () => {
    const e = editor()
    fireEvent.pointerDown(e.hit, { button: 0, pointerId: 1, clientX: 370, clientY: 470 })
    fireEvent.pointerUp(e.hit, { button: 0, pointerId: 1, clientX: 370, clientY: 470 })
    const bar = await waitFor(() => { const b = e.container.querySelector('[data-handle="row-gap"]'); if (!b) throw new Error('no bar yet'); return b })
    fireEvent.pointerDown(bar, { button: 0, pointerId: 2, clientX: 400, clientY: 500 })
    fireEvent.pointerMove(bar, { pointerId: 2, clientX: 400, clientY: 532 })
    fireEvent.pointerUp(bar, { pointerId: 2, clientX: 400, clientY: 532 })
    await waitFor(() => expect(e.api.calls.filter((c) => c.method === 'PUT')).toHaveLength(1))
    expect(e.api.calls.find((c) => c.method === 'PUT')!.body).toEqual({ rows: [row('1', 0), row('2', 2)], x: 25, y: 51.6 })
  })
})
