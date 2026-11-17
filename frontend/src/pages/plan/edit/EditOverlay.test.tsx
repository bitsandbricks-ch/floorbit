import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { EditOverlay } from './EditOverlay'
import type { ItemRef } from './geometry'

const shape = (id: string, cx: number) => ({ id, group: null, cx, cy: 100, rotation: 0, w: 100, h: 40, name: id, cells: [] })
const data = {
  size: { w: 1600, h: 1000, cell: 32 }, seats: {}, blocks: [], halls: [], hall: 'main', switches: [],
  drawing: { shapes: [shape('A', 100), shape('B', 400)], marks: [], box: { x: 0, y: 0, w: 1600, h: 1000 }, cell: 32 },
} as unknown as SeatViewData
const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }
const A: ItemRef = { kind: 'block', id: 'A' }, B: ItemRef = { kind: 'block', id: 'B' }

function overlay(props: Partial<React.ComponentProps<typeof EditOverlay>> = {}) {
  const onSelect = vi.fn(), onDrop = vi.fn()
  const view = render(
    <svg><EditOverlay ctx={ctx} data={data} selection={[]} onSelect={onSelect} onDrag={() => {}} onDrop={onDrop} space={false} {...props} /></svg>,
  )
  const hit = (id: string) => view.container.querySelector(`[data-item="block:${id}"]`)!
  return { onSelect, onDrop, hit, view }
}

describe('Edit overlay', () => {
  it('selects the item clicked', () => {
    const { onSelect, hit } = overlay()
    fireEvent.pointerDown(hit('A'), { button: 0, pointerId: 1, clientX: 100, clientY: 100 })
    expect(onSelect).toHaveBeenCalledWith([A])
  })

  it('leaves the pointer to the plan with the Hand tool, so a drag moves the view', () => {
    const { onSelect, hit, view } = overlay({ tool: 'hand' })
    expect(view.container.querySelector('.fb-edit')).toHaveClass('panning')
    fireEvent.pointerDown(hit('A'), { button: 0, pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerUp(hit('A'), { button: 0, pointerId: 1, clientX: 140, clientY: 100 })
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('adds with Shift, and takes a whole group out again', () => {
    const together = (r: ItemRef) => (r.id === 'B' ? [A, B] : [r])
    const added = overlay({ selection: [A] })
    fireEvent.pointerDown(added.hit('B'), { button: 0, pointerId: 1, shiftKey: true, clientX: 400, clientY: 100 })
    expect(added.onSelect).toHaveBeenCalledWith([A, B])
    added.view.unmount()
    const taken = overlay({ selection: [A, B], together })
    fireEvent.pointerDown(taken.hit('B'), { button: 0, pointerId: 1, shiftKey: true, clientX: 400, clientY: 100 })
    expect(taken.onSelect).toHaveBeenCalledWith([])
  })

  it('drops a drag by how far the pointer went', () => {
    const { onDrop, hit } = overlay({ selection: [A] })
    fireEvent.pointerDown(hit('A'), { button: 0, pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerMove(hit('A'), { pointerId: 1, clientX: 140, clientY: 130 })
    fireEvent.pointerUp(hit('A'), { pointerId: 1, clientX: 140, clientY: 130 })
    expect(onDrop).toHaveBeenCalledWith({ x: 40, y: 30 }, true, A, 1)
  })

  it('places on the grid, or where clicked with snapping to the grid off', () => {
    const onPlace = vi.fn()
    const on = overlay({ tool: 'text', onPlace })
    const bg = () => on.view.container.querySelector('.fb-edit-bg')!
    fireEvent.pointerDown(bg(), { button: 0, pointerId: 1, clientX: 803, clientY: 502 })
    expect(onPlace.mock.calls[0][0]).toEqual({ x: 800, y: 500 })
    on.view.unmount()
    const off = overlay({ tool: 'text', onPlace, snapping: { grid: false, items: true } })
    fireEvent.pointerDown(off.view.container.querySelector('.fb-edit-bg')!, { button: 0, pointerId: 1, clientX: 803, clientY: 502 })
    expect(onPlace.mock.calls[1][0]).toEqual({ x: 803, y: 502 })
  })

  it('measures with the Measure tool and keeps the line until the next one, saving nothing', () => {
    const onLine = vi.fn()
    const { view } = overlay({ tool: 'measure', onLine })
    const bg = view.container.querySelector('.fb-edit-bg')!
    fireEvent.pointerDown(bg, { button: 0, pointerId: 1, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(bg, { pointerId: 1, clientX: 128, clientY: 0 })
    fireEvent.pointerUp(bg, { pointerId: 1, clientX: 128, clientY: 0 })
    expect(onLine).not.toHaveBeenCalled()
    expect(view.container.querySelector('.fb-edit-draft text')).toHaveTextContent('4 · 0°')
  })
})
