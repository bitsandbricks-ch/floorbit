import { describe, expect, it } from 'vitest'
import type { PlanCable, PlanDrawing } from '@/api/types'
import { bundles, followPlan, plugAt } from './cableRoute'

// Block A of tests/test_cable_plan.py: 12 x 2 seats at 40 %, 40 % of a 1600 x 1000 plan (cell 32).
const size = { w: 1600, h: 1000, cell: 32 }
const cells = Array.from({ length: 24 }, (_, i) => ({
  seat: `A-${i + 1}`, x: (i % 12) * 32 - 192, y: Math.floor(i / 12) * 32 - 32, hit: false, on: null,
}))
const drawing = { shapes: [{ cx: 640, cy: 400, rotation: 0, w: 384, h: 64, name: 'A', cells }], box: '0 0 1600 1000', cell: 32 } as unknown as PlanDrawing
const cable = (seat: string, points: [number, number][], extra: Partial<PlanCable> = {}): PlanCable => ({
  key: `lan:sw|${seat}`, kind: 'lan', layer: 'network', points, manual: false, corners: 'square', via: null, label: '',
  ref: { cable: 'c1', switch: 'sw-a-02', seat }, ...extra,
})
const at = (x: number, y: number) => ({ id: 'sw', name: 'sw-a-02', status: 'up', x: (x / 100) * 1600, y: (y / 100) * 1000 })

describe('followPlan', () => {
  it('keeps the server route while nothing moved', () => {
    const c = cable('A-2', [[36, 20], [36, 35.2], [31, 35.2], [31, 38.4]])
    expect(followPlan([c], { drawing, switches: [at(36, 20)], size })[0]).toBe(c)
  })

  it('routes again at once when the switch moved, the same way the server does', () => {
    const c = cable('A-14', [[36, 20], [36, 35.2], [27, 35.2], [27, 44.8], [31, 44.8], [31, 41.6]])
    // The switch went to the left of the block: in along the block's left side.
    const [moved] = followPlan([c], { drawing, switches: [at(10, 20)], size })
    expect(moved.points).toEqual([[10, 20], [27, 20], [27, 41.6], [31, 41.6]])
  })

  it('moves only the ends of a cable the crew bent by hand', () => {
    const c = cable('A-2', [[36, 20], [50, 30], [31, 38.4]], { manual: true })
    const [moved] = followPlan([c], { drawing, switches: [at(12, 22)], size })
    expect(moved.points).toEqual([[12, 22], [50, 30], [31, 38.4]])
  })
})

describe('bundles', () => {
  it('counts the cables sharing a run and leaves single cables alone', () => {
    const run = (x: number) => cable(`A-${x}`, [[36, 20], [36, 35.2], [x, 35.2], [x, 38.4]], { key: `k${x}` })
    const out = bundles([run(29), run(31), run(33)], size)
    // Down from the switch all three; along the top three as far as A-3's drop (x 33 %), then fewer.
    expect(out).toContainEqual({ x1: 576, y1: 200, x2: 576, y2: 352, count: 3, label: true })
    expect(out).toContainEqual({ x1: 528, y1: 352, x2: 576, y2: 352, count: 3, label: true })
    expect(out).toHaveLength(2)
  })
})

describe('plugAt', () => {
  it('puts the plug on the seat edge the cable comes in from', () => {
    const c = cable('A-2', [[36, 20], [36, 35.2], [31, 35.2], [31, 38.4]])
    const [x, y] = plugAt(c, size, 32)!
    expect(x).toBeCloseTo(496)
    expect(y).toBeCloseTo(384 - 32 * 0.45)
  })
})
