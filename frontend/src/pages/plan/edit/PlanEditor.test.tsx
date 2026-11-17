import { fireEvent, screen, waitFor } from '@testing-library/react'
import { notifications } from '@mantine/notifications'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { LayerState } from '../layers'
import type { View } from '../model'
import { PlanEditor } from './PlanEditor'

// Notifications live in one store for the whole file: earlier steps' toasts would queue later ones.
afterEach(() => { vi.unstubAllGlobals(); notifications.clean() })

// Two seat blocks, A at a quarter of the plan's width, B at half: 1600 × 1000 drawing units.
const shape = (id: string, cx: number) => ({ id, group: null, cx, cy: 500, rotation: 0, w: 128, h: 32, name: id, cells: [] })
const data = {
  halls: [{ id: 'main', name: 'Hall', seats: 0, online: 0, problems: 0 }], hall: 'main', seats: {}, blocks: [], switches: [],
  size: { w: 1600, h: 1000, cell: 32 }, background: null,
  drawing: { shapes: [shape('A', 400), shape('B', 800)], marks: [], box: '0 0 1600 1000', cell: 32 },
} as unknown as SeatViewData
const layers: LayerState = { on: new Set(), fade: {} }
const blockRow = (id: string, x: number) => ({ id, name: id, x, y: 50, rotation: 0, rows: 1, cols: 4, hall_id: 'main' })

function editor(routes: Record<string, unknown> = {}) {
  const api = fakeFetch({
    'GET /api/plan-groups?hall=main': { groups: [] },
    'GET /api/power/markers': { enabled: false, boards: [], feeds: [] },
    'GET /api/cable-plan?hall=main': { cables: [], panels: [] },
    'PUT /api/seat-blocks/A': { ok: true },
    'PUT /api/seat-blocks/B': { ok: true },
    ...routes,
  })
  vi.stubGlobal('fetch', api.fn)
  const setView = vi.fn()
  const refresh = vi.fn(() => Promise.resolve())
  const view: View = { x: 0, y: 0, w: 1600, h: 1000 }
  const r = renderWithApp(
    <PlanEditor data={data} view={view} setView={setView} layers={layers} refresh={refresh} onHall={() => {}} onShortcuts={() => {}} />,
  )
  const plan = r.container.querySelector('.fb-plan-editor')!
  const hit = (id: string) => r.container.querySelector(`[data-item="block:${id}"]`)!
  const select = (id: string, shiftKey = false) => fireEvent.pointerDown(hit(id), { button: 0, pointerId: 1, shiftKey, clientX: 0, clientY: 0 })
  const key = (k: string, mods: { ctrlKey?: boolean; shiftKey?: boolean } = {}) => fireEvent.keyDown(plan, { key: k, ...mods })
  const sent = (method: string) => api.calls.filter((c) => c.method === method)
  return { ...r, api, plan, hit, select, key, sent, setView, refresh }
}

describe('Plan editor keys', () => {
  it('nudges the selection with the arrow keys, five times as far with Shift', async () => {
    const e = editor()
    e.select('A')
    e.key('ArrowRight')
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(1))
    expect(e.sent('PUT')[0]).toMatchObject({ path: '/api/seat-blocks/A', body: { x: 25.5, y: 50 } })
    e.key('ArrowDown', { shiftKey: true })
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(2))
    expect(e.sent('PUT')[1].body).toEqual({ x: 25, y: 52.5 })
  })

  it('moves everything with Ctrl+A, and undoes and redoes it as one step', async () => {
    const e = editor()
    e.key('a', { ctrlKey: true })
    e.key('ArrowLeft')
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(2))
    expect(e.sent('PUT').map((c) => c.path).sort()).toEqual(['/api/seat-blocks/A', '/api/seat-blocks/B'])
    e.key('z', { ctrlKey: true })
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(4))
    expect(e.sent('PUT').slice(2).map((c) => c.body)).toEqual(expect.arrayContaining([{ x: 25, y: 50 }, { x: 50, y: 50 }]))
    e.key('z', { ctrlKey: true, shiftKey: true })
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(6))
    expect(e.sent('PUT').slice(4).map((c) => c.body)).toEqual(expect.arrayContaining([{ x: 24.5, y: 50 }, { x: 49.5, y: 50 }]))
  })

  it('turns a block a quarter with R and back with Shift+R', async () => {
    const e = editor()
    e.select('B')
    e.key('r')
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(1))
    expect(e.sent('PUT')[0]).toMatchObject({ path: '/api/seat-blocks/B', body: { rotation: 90 } })
    e.key('R', { shiftKey: true })
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(2))
    expect(e.sent('PUT')[1].body).toEqual({ rotation: 270 })
  })

  it('shows what the right-click menu does as buttons once something is selected', async () => {
    const e = editor()
    expect(screen.queryByRole('toolbar', { name: 'Selection' })).toBeNull()
    e.select('B')
    const bar = await screen.findByRole('toolbar', { name: 'Selection' })
    expect(bar).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Turn 90°' }))
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(1))
    expect(e.sent('PUT')[0]).toMatchObject({ path: '/api/seat-blocks/B', body: { rotation: 90 } })
  })

  it('takes the Hand tool with H: a click on a block no longer selects it', async () => {
    const e = editor()
    e.key('h')
    expect(await screen.findByRole('button', { name: 'Hand', pressed: true })).toBeInTheDocument()
    e.select('A')
    expect(screen.queryByRole('toolbar', { name: 'Selection' })).toBeNull()
    e.key('Escape')
    expect(await screen.findByRole('button', { name: 'Select', pressed: true })).toBeInTheDocument()
  })

  it('deletes with Delete and brings the block back with Ctrl+Z', async () => {
    const e = editor({
      'GET /api/seat-blocks?hall=main': [blockRow('A', 25), blockRow('B', 50)],
      'DELETE /api/seat-blocks/A': { ok: true },
      'POST /api/seat-blocks': { id: 'A2' },
    })
    e.select('A')
    e.key('Delete')
    await waitFor(() => expect(e.sent('DELETE')).toHaveLength(1))
    expect(e.sent('DELETE')[0].path).toBe('/api/seat-blocks/A')
    e.key('z', { ctrlKey: true })
    await waitFor(() => expect(e.sent('POST')).toHaveLength(1))
    expect(e.sent('POST')[0].body).toMatchObject({ name: 'A', hall_id: 'main' })
  })

  it('zooms to the selection with F and leaves the view alone with nothing selected', () => {
    const e = editor()
    e.key('f')
    expect(e.setView).not.toHaveBeenCalled()
    e.select('A')
    e.key('f')
    const v = e.setView.mock.calls[0][0] as View
    expect(v.x).toBeLessThan(400 - 64)
    expect(v.x + v.w).toBeGreaterThan(400 + 64)
    expect(v.w).toBeLessThan(1600)
  })

  it('drops the selection with Esc, so the arrow keys move nothing', async () => {
    const e = editor()
    e.select('A')
    e.key('Escape')
    e.key('ArrowUp')
    await new Promise((r) => setTimeout(r, 20))
    expect(e.sent('PUT')).toHaveLength(0)
  })

  it('leaves keys alone while a field has the focus', async () => {
    const e = editor()
    e.select('A')
    const input = document.createElement('input')
    e.plan.appendChild(input)
    fireEvent.keyDown(input, { key: 'Delete' })
    fireEvent.keyDown(input, { key: 'ArrowRight' })
    await new Promise((r) => setTimeout(r, 20))
    expect(e.api.calls.filter((c) => c.method !== 'GET')).toHaveLength(0)
  })
})

describe('Plan editor: select all like this', () => {
  it('picks every block with Ctrl+Shift+A, so one arrow press moves them all', async () => {
    const e = editor()
    e.select('A')
    e.key('A', { ctrlKey: true, shiftKey: true })
    e.key('ArrowUp')
    await waitFor(() => expect(e.sent('PUT')).toHaveLength(2))
    expect(e.sent('PUT').map((c) => c.path).sort()).toEqual(['/api/seat-blocks/A', '/api/seat-blocks/B'])
  })
})

describe('Plan editor: copies and failures', () => {
  const rows = { 'GET /api/seat-blocks?hall=main': [blockRow('A', 25), blockRow('B', 50)], 'GET /api/seat-blocks': [blockRow('A', 25), blockRow('B', 50)],
    'GET /api/options/panels': { options: [] }, 'POST /api/seat-blocks': { id: 'C1' }, 'DELETE /api/seat-blocks/C1': { ok: true } }

  it('duplicates with Ctrl+D under a new name, and Ctrl+Z deletes the copy again', async () => {
    const e = editor(rows)
    e.select('A')
    e.key('d', { ctrlKey: true })
    await waitFor(() => expect(e.sent('POST')).toHaveLength(1))
    const body = e.sent('POST')[0].body as { name: string; x: number; hall_id: string }
    expect(body.hall_id).toBe('main')
    expect(body.name).not.toBe('A')
    expect(body.name).not.toBe('B')
    expect(body.x).toBeGreaterThan(25)
    e.key('z', { ctrlKey: true })
    await waitFor(() => expect(e.sent('DELETE')).toHaveLength(1))
    expect(e.sent('DELETE')[0].path).toBe('/api/seat-blocks/C1')
  })

  it('copies with Ctrl+C and pastes a copy with Ctrl+V', async () => {
    localStorage.removeItem('floorbit-plan-clipboard')
    const e = editor(rows)
    e.select('B')
    e.key('c', { ctrlKey: true })
    await waitFor(() => expect(localStorage.getItem('floorbit-plan-clipboard')).toContain('"B"'))
    e.key('v', { ctrlKey: true })
    await waitFor(() => expect(e.sent('POST')).toHaveLength(1))
    expect((e.sent('POST')[0].body as { name: string }).name).not.toBe('B')
  })

  it('says so when the server refuses a change, and keeps nothing to undo', async () => {
    const e = editor({ 'PUT /api/seat-blocks/A': () => ({ status: 409, body: { error: 'Seats overlap block B' } }) })
    e.select('A')
    e.key('ArrowRight')
    expect(await screen.findByText('Seats overlap block B')).toBeInTheDocument()
    expect(screen.getByText('Not saved')).toBeInTheDocument()
    e.key('z', { ctrlKey: true })
    await new Promise((r) => setTimeout(r, 20))
    expect(e.sent('PUT')).toHaveLength(1)
  })
})
