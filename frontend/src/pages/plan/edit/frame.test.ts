import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { frameOf } from './frame'

const shape = (id: string, cx: number, cy: number, w: number, h: number, rotation = 0) => ({ id, cx, cy, w, h, rotation })
const data = {
  switches: [{ id: 's', x: 1500, y: 900 }],
  drawing: { shapes: [shape('a', 200, 200, 300, 60), shape('tall', 800, 500, 300, 60, 90)], marks: [] },
} as unknown as SeatViewData
const screen = { x: 0, y: 0, w: 1600, h: 800 }

describe('framing the selection with F', () => {
  it('fits the items with room around them, in the screen shape', () => {
    const v = frameOf(data, [{ kind: 'block', id: 'a' }, { kind: 'switch', id: 's' }], screen)!
    expect(v.h / v.w).toBeCloseTo(0.5)
    expect(v.x).toBeLessThan(200 - 156)
    expect(v.x + v.w).toBeGreaterThan(1512)
    expect(v.y).toBeLessThan(200 - 36)
    expect(v.y + v.h).toBeGreaterThan(912)
  })
  it('counts a turned block as turned', () => {
    const v = frameOf(data, [{ kind: 'block', id: 'tall' }], { x: 0, y: 0, w: 100, h: 100 })!
    // 312 tall once turned (300 + padding): a square view of at least that.
    expect(v.h).toBeGreaterThanOrEqual(312 * 1.2 - 0.001)
  })
  it('does not zoom closer than the plan allows, and skips missing items', () => {
    expect(frameOf(data, [{ kind: 'switch', id: 's' }], screen)!.w).toBe(240)
    expect(frameOf(data, [{ kind: 'block', id: 'gone' }], screen)).toBeNull()
  })
})
