import { describe, expect, it } from 'vitest'
import type { PlanCable, PlanDrawing } from '@/api/types'
import { followPlan, plugAt, spread } from './cableRoute'

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

describe('followPlan with lanes', () => {
  // The same block with its rows touching: the cables run along the seam between them (y 40 %).
  const laned = {
    ...drawing,
    shapes: [{ ...drawing.shapes[0], cells: cells.map((c, i) => ({ ...c, lane: i < 12 ? 16 : -16 })) }],
  } as unknown as PlanDrawing
  it('routes into the lane as the server does (tests/test_cable_plan.py)', () => {
    const c = cable('A-14', [[36, 20], [36, 35.2], [31, 35.2], [31, 41.6]])
    const [moved] = followPlan([c], { drawing: laned, switches: [at(10, 20)], size })
    expect(moved.points).toEqual([[10, 20], [27, 20], [27, 40], [31, 40], [31, 41.6]])
    const [above] = followPlan([{ ...c, points: [[50, 20], ...c.points.slice(1)] }], { drawing: laned, switches: [at(36, 20)], size })
    expect(above.points).toEqual([[36, 20], [36, 35.2], [27, 35.2], [27, 40], [31, 40], [31, 41.6]])
  })
})

describe('followPlan along a bent row', () => {
  // The U of tests/test_cable_lanes_bent.py: 8 seats at 40 %, 40 %, its lane outside (issue #1208).
  const lane: [number, number][] = [[-112, -64], [-112, -32], [-112, 0], [-112, 64], [-48, 64], [-16, 64], [16, 64], [48, 64], [112, 64], [112, 0], [112, -32], [112, -64]]
  const u = [
    { seat: 'U-1', x: -96, y: -48, a: 90, li: 1 }, { seat: 'U-2', x: -96, y: -16, a: 90, li: 2 },
    { seat: 'U-3', x: -64, y: 16, li: 4 }, { seat: 'U-4', x: -32, y: 16, li: 5 }, { seat: 'U-5', x: 0, y: 16, li: 6 },
    { seat: 'U-6', x: 32, y: 16, li: 7 }, { seat: 'U-7', x: 64, y: -16, a: -90, li: 9 }, { seat: 'U-8', x: 64, y: -48, a: -90, li: 10 },
  ].map((c, n) => ({ ...c, hit: false, on: null, side: 'left', rc: [0, n] }))
  const bent = { shapes: [{ cx: 640, cy: 400, rotation: 0, w: 192, h: 96, name: 'U', cells: u, lanes: { 0: lane } }], box: '0 0 1600 1000', cell: 32 } as unknown as PlanDrawing

  it('runs round the U to the seat the way the server does', () => {
    const c = cable('U-4', [[50, 20], [39, 43.2]])
    const [moved] = followPlan([c], { drawing: bent, switches: [at(10, 20)], size })
    expect(moved.points).toEqual([[10, 20], [33, 20], [33, 46.4], [39, 46.4], [39, 43.2]])
  })

  it('comes in at the end nearer the switch', () => {
    const c = cable('U-8', [[50, 20], [45, 36.8]])
    const [moved] = followPlan([c], { drawing: bent, switches: [at(60, 20)], size })
    expect(moved.points[moved.points.length - 1]).toEqual([45, 36.8])
    expect(moved.points.slice(1).every(([x]) => x >= 47 - 1e-6 || x === 45)).toBe(true)
  })
})

describe('spread', () => {
  const run = (x: number) => cable(`A-${x}`, [[36, 20], [36, 35.2], [x, 35.2], [x, 38.4]], { key: `k${x}` })
  const px = (c: PlanCable) => c.points.map(([x, y]) => [Math.round((x / 100) * 1600 * 10) / 10, Math.round((y / 100) * 1000 * 10) / 10])

  it('draws cables that share a run side by side, with one count per run', () => {
    const { cables: out, bundles } = spread([run(29), run(31), run(33)], size, 32)
    // Down from the switch all three, then along the top: one count on each run.
    expect(bundles).toHaveLength(2)
    expect(bundles).toContainEqual({ x1: 576, y1: 200, x2: 576, y2: 352, count: 3 })
    expect(bundles).toContainEqual({ x1: 528, y1: 352, x2: 576, y2: 352, count: 3 })
    // Every cable still starts at its switch and ends at its seat...
    for (const c of out) {
      expect(c.points[0]).toEqual([36, 20])
      expect(c.points[c.points.length - 1][1]).toBe(38.4)
    }
    // ...but the runs no longer lie on top of each other.
    const lanes = out.map((c) => px(c)[2][1])
    expect(new Set(lanes).size).toBe(3)
  })

  it('lets the cable that turns off first run on the side it turns to', () => {
    const { cables: out } = spread([run(29), run(31), run(33)], size, 32)
    // Coming down the right of the block and turning left, A-3 (x 33 %) leaves first: it runs on the
    // outside of the bend, lowest along the top, so it drops to its seat without crossing the others.
    const along = (c: PlanCable) => px(c)[2][1]
    const [a1, a2, a3] = out.map(along)
    expect(a3).toBeGreaterThan(a2)
    expect(a2).toBeGreaterThan(a1)
    // The drop into each seat stays straight down at the seat.
    for (const c of out) expect(px(c).at(-2)![0]).toBe(px(c).at(-1)![0])
  })

  it('leaves a lone cable and straight cables alone', () => {
    const one = run(29)
    expect(spread([one], size).cables[0]).toBe(one)
    const straight = { ...run(31), corners: 'straight' as const, points: [[36, 20], [31, 38.4]] as [number, number][] }
    expect(spread([straight, { ...straight, key: 'other' }], size).bundles).toEqual([])
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
