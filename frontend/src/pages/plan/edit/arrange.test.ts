import { describe, expect, it } from 'vitest'
import type { PlanGroup, SeatViewData } from '@/api/types'
import { alignMoves, distributeMoves, groupsOf, regrouped, snapToGuides, withGroups } from './arrange'

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

  it('picks plan groups of any items, and the block groups they reach', () => {
    const groups: PlanGroup[] = [{ id: 'p', name: 'P', members: [{ kind: 'mark', id: 'm' }, { kind: 'block', id: 'b' }] }]
    const got = withGroups(data, [{ kind: 'mark', id: 'm' }], groups).map((x) => `${x.kind}:${x.id}`)
    expect(got.sort()).toEqual(['block:a', 'block:b', 'mark:m'])
  })

  it('makes and takes apart groups', () => {
    const m = (id: string) => ({ kind: 'mark' as const, id })
    const groups: PlanGroup[] = [{ id: 'old', name: 'Old', members: [m('x'), m('y')] }, { id: 'keep', name: 'K', members: [m('p'), m('q'), m('s')] }]
    const made = regrouped(groups, [m('y'), m('s'), { kind: 'cable', id: 'c' }], { id: 'new', name: 'New' })
    expect(made.map((g) => [g.id, g.members.map((x) => x.id)])).toEqual([['keep', ['p', 'q']], ['new', ['y', 's']]])
    expect(groupsOf(made, [m('p')]).map((g) => g.id)).toEqual(['keep'])
    expect(regrouped(made, [m('p')]).map((g) => g.id)).toEqual(['new'])
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
