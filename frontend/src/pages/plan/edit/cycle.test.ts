import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { nextItem, readingOrder } from './cycle'

const shape = (id: string, cx: number, cy: number) => ({ id, group: null, cx, cy, rotation: 0, w: 100, h: 40, name: id, cells: [] })
const data = {
  size: { w: 1600, h: 1000, cell: 32 }, switches: [{ id: 's', name: 'sw', status: 'up', x: 50, y: 50 }], seats: {}, blocks: [], halls: [], hall: 'main',
  drawing: { shapes: [shape('low', 100, 400), shape('right', 600, 100), shape('left', 200, 110)], marks: [], box: { x: 0, y: 0, w: 1600, h: 1000 }, cell: 32 },
} as unknown as SeatViewData

describe('going through the plan with Tab', () => {
  it('reads by rows, then left to right', () => {
    expect(readingOrder(data).map((r) => r.id)).toEqual(['s', 'left', 'right', 'low'])
  })
  it('steps forward and back, wrapping around', () => {
    expect(nextItem(data, null)?.id).toBe('s')
    expect(nextItem(data, { kind: 'block', id: 'left' })?.id).toBe('right')
    expect(nextItem(data, { kind: 'block', id: 'low' })?.id).toBe('s')
    expect(nextItem(data, { kind: 'switch', id: 's' }, true)?.id).toBe('low')
  })
})
