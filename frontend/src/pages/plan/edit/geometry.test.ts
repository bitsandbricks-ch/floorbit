import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { inside, movePatch, moved, outlineOf, snappedDelta } from './geometry'

const data = {
  halls: [], hall: 'main', size: { w: 1600, h: 1000, cell: 32 }, background: null, seats: {}, blocks: [],
  monitoring: true, checkin: false, last_read: null,
  switches: [{ id: 'sw1', name: 'sw-a', status: 'online', x: 160, y: 100 }],
  drawing: {
    box: '0 0 1600 1000', cell: 32,
    shapes: [{ id: 'b1', cx: 400, cy: 300, rotation: 0, w: 128, h: 32, name: 'A', cells: [] }],
    marks: [
      { id: 'w1', kind: 'wall', x: 100, y: 100, x2: 300, y2: 100 },
      { id: 't1', kind: 'text', x: 800, y: 50, text: 'Stage' },
    ],
  },
} as unknown as SeatViewData

describe('editor geometry', () => {
  it('snaps the lead item to the 0.5 % grid', () => {
    // 400 px is 25 %; +13 px is 25.8 %, which snaps to 26 % = 416 px.
    expect(snappedDelta(data, { kind: 'block', id: 'b1' }, { x: 13, y: 0 }, true)).toEqual({ x: 16, y: 0 })
    expect(snappedDelta(data, { kind: 'block', id: 'b1' }, { x: 13, y: 0 }, false)).toEqual({ x: 13, y: 0 })
  })

  it('moves blocks, walls (both ends) and switches together', () => {
    const items = [{ kind: 'block' as const, id: 'b1' }, { kind: 'mark' as const, id: 'w1' }, { kind: 'switch' as const, id: 'sw1' }]
    const out = moved(data, items, { x: 16, y: 10 })
    expect(out.drawing!.shapes[0]).toMatchObject({ cx: 416, cy: 310 })
    expect(out.drawing!.marks![0]).toMatchObject({ x: 116, y: 110, x2: 316, y2: 110 })
    expect(out.drawing!.marks![1]).toMatchObject({ x: 800, y: 50 })
    expect(out.switches[0]).toMatchObject({ x: 176, y: 110 })
  })

  it('saves positions in % of the plan', () => {
    expect(movePatch(data, { kind: 'block', id: 'b1' }, { x: 16, y: 10 })).toEqual({ x: 26, y: 31 })
    expect(movePatch(data, { kind: 'mark', id: 'w1' }, { x: 0, y: 0 })).toEqual({ x: 6.25, y: 10, x2: 18.75, y2: 10 })
    expect(movePatch(data, { kind: 'switch', id: 'nope' }, { x: 0, y: 0 })).toBeNull()
  })

  it('outlines a block with its padding and selects by box', () => {
    expect(outlineOf(data, { kind: 'block', id: 'b1' })!.box).toEqual({ x: 330, y: 278, w: 140, h: 44 })
    const got = inside(data, { x: 0, y: 0, w: 500, h: 400 }).map((r) => r.id)
    expect(got.sort()).toEqual(['b1', 'sw1', 'w1'])
  })
})
