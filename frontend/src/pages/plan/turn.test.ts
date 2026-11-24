import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { turnHelps, turnPlan } from './turn'

const data = {
  halls: [], hall: 'h', size: { w: 1000, h: 625, cell: 20 }, background: '/bg.png', background_frame: { x: 0, y: 0, w: 1, h: 1 },
  switches: [{ id: 's', name: 'sw', status: 'up', x: 100, y: 50 }], seats: {}, blocks: [], monitoring: false, checkin: false, last_read: null,
  drawing: {
    box: '0 0 200 400', cell: 20,
    shapes: [{ cx: 100, cy: 300, rotation: 0, w: 100, h: 40, name: '', cells: [] }],
    marks: [
      { kind: 'zone', x: 10, y: 20, w: 50, h: 30 },
      { kind: 'wall', x: 0, y: 0, x2: 0, y2: 100, points: [[0, 50]] },
      { kind: 'text', x: 5, y: 6, text: 'Stage', rotation: 0 },
    ],
  },
} as unknown as SeatViewData

describe('turnPlan', () => {
  const out = turnPlan(data)
  it('turns the box so a tall hall becomes wide', () => {
    expect(out.drawing!.box).toBe('0 -200 400 200')
  })
  it('turns blocks a quarter left, top ending up on the left', () => {
    expect(out.drawing!.shapes[0]).toMatchObject({ cx: 300, cy: -100, rotation: -90 })
    expect(out.switches[0]).toMatchObject({ x: 50, y: -100 })
  })
  it('swaps a zone\'s sides around its middle and keeps text upright', () => {
    expect(out.drawing!.marks![0]).toMatchObject({ x: 20, y: -60, w: 30, h: 50 })
    expect(out.drawing!.marks![1]).toMatchObject({ x: 0, y: -0, x2: 100, y2: -0, points: [[50, -0]] })
    expect(out.drawing!.marks![2]).toMatchObject({ x: 6, y: -5, rotation: 0 })
  })
  it('leaves the background picture out', () => {
    expect(out.background).toBeNull()
  })
})

describe('turnHelps', () => {
  it('turns a tall hall in a wide box, not a wide one', () => {
    expect(turnHelps({ w: 200, h: 400 }, { w: 960, h: 400 })).toBe(true)
    expect(turnHelps({ w: 400, h: 200 }, { w: 960, h: 400 })).toBe(false)
    expect(turnHelps({ w: 200, h: 210 }, { w: 960, h: 400 })).toBe(false)
  })
})
