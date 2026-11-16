import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { alignMoves, distributeMoves, snapToGuides, withGroups } from './arrange'

const shape = (id: string, cx: number, cy: number, group: string | null = null) =>
  ({ id, group, cx, cy, rotation: 0, w: 100, h: 40, name: id, cells: [] })
const data = {
  size: { w: 1600, h: 1000, cell: 32 }, switches: [], seats: {}, blocks: [], halls: [], hall: 'main', background: null,
  monitoring: false, checkin: false, last_read: null,
  drawing: { shapes: [shape('a', 100, 100, 'g'), shape('b', 300, 120, 'g'), shape('c', 600, 200)], marks: [], box: { x: 0, y: 0, w: 1600, h: 1000 }, cell: 32 },
} as unknown as SeatViewData
const r = (id: string) => ({ kind: 'block' as const, id })

describe('arranging items', () => {
  it('picks and drops groups whole', () => {
    expect(withGroups(data, [r('a')]).map((x) => x.id)).toEqual(['a', 'b'])
    expect(withGroups(data, [r('c')]).map((x) => x.id)).toEqual(['c'])
  })

  it('lines items up on the selection edge', () => {
    const moves = alignMoves(data, [r('a'), r('c')], 'top')
    // Outlines have 6 units of padding: a's top is 74, c's 174.
    expect(moves).toEqual([[r('c'), { x: 0, y: -100 }]])
  })

  it('spreads items with equal gaps', () => {
    const moves = distributeMoves(data, [r('a'), r('b'), r('c')], 'x')
    // Spans 44..656 with three 112 wide outlines: gaps of 138, so b's left goes to 294.
    expect(moves).toEqual([[r('b'), { x: 50, y: 0 }]])
  })

  it('snaps to another item edge within reach', () => {
    const { d, guides } = snapToGuides(data, [r('c')], { x: 0, y: -97 }, 5, [r('a'), r('b'), r('c')])
    expect(d.y).toBe(-100)
    expect(guides).toContainEqual({ axis: 'y', at: 74 })
  })
})
