import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { angleTo, canTurnOne, quarterTurns } from './turn'

const data = {
  drawing: {
    shapes: [{ id: 'a', rotation: 270 }, { id: 'b', rotation: 0 }],
    marks: [{ id: 't', kind: 'text', rotation: 90 }, { id: 'i', kind: 'icon' }, { id: 'z', kind: 'zone' }, { id: 'w', kind: 'wall' }],
  },
} as unknown as SeatViewData

describe('turning the selection with R', () => {
  it('turns blocks, labels and icons a quarter turn, wrapping at 360', () => {
    const refs = [{ kind: 'block', id: 'a' }, { kind: 'mark', id: 't' }, { kind: 'mark', id: 'i' }] as const
    expect(quarterTurns(data, [...refs]).map(([r, b, a]) => [r.id, b.rotation, a.rotation])).toEqual([['a', 270, 0], ['t', 90, 180], ['i', 0, 90]])
  })
  it('turns back the other way', () => {
    expect(quarterTurns(data, [{ kind: 'block', id: 'b' }], true)[0][2]).toEqual({ rotation: 270 })
  })
  it('turns zones too, and leaves walls, switches and gone items out', () => {
    expect(quarterTurns(data, [{ kind: 'mark', id: 'z' }]).map(([, , a]) => a)).toEqual([{ rotation: 90 }])
    expect(quarterTurns(data, [{ kind: 'mark', id: 'w' }, { kind: 'switch', id: 's' }, { kind: 'block', id: 'gone' }])).toEqual([])
    expect(canTurnOne(data, { kind: 'mark', id: 'z' })).toBe(true)
    expect(canTurnOne(data, { kind: 'mark', id: 'w' })).toBe(false)
  })
  it('reads the rotate handle clockwise from up, in 15° steps with Shift', () => {
    const c = { x: 0, y: 0 }
    expect(angleTo(c, { x: 0, y: -10 }, false)).toBe(0)
    expect(angleTo(c, { x: 10, y: 0 }, false)).toBe(90)
    expect(angleTo(c, { x: -10, y: 0 }, false)).toBe(270)
    expect(angleTo(c, { x: 10, y: -9 }, false)).toBe(48)
    expect(angleTo(c, { x: 10, y: -9 }, true)).toBe(45)
  })
})
