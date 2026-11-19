import { describe, expect, it } from 'vitest'
import { add, compact, overlap, place, rows, snapHeight, stepHeight } from './grid'

const empty = { pane: { kind: 'empty' as const } }
const box = (x: number, y: number, w: number, h: number) => ({ x, y, w, h, node: empty })
const at = (ps: { x: number; y: number }[]) => ps.map((p) => [p.x, p.y])

describe('dashboard grid', () => {
  it('floats panels up without overlap', () => {
    const out = compact([box(0, 5, 12, 4), box(0, 20, 12, 4), box(12, 3, 12, 2)])
    expect(at(out)).toEqual([[0, 0], [0, 4], [12, 0]])
    expect(rows(out)).toBe(8)
  })

  it('swaps two stacked panels past the middle, in both directions', () => {
    const two = [box(0, 0, 12, 6), box(0, 6, 12, 6)]
    expect(at(place(two, 0, { y: 4 }))).toEqual([[0, 0], [0, 6]])   // not yet past the middle
    expect(at(place(two, 0, { y: 10 }))).toEqual([[0, 6], [0, 0]])
    expect(at(place(two, 1, { y: 3 }))).toEqual([[0, 6], [0, 0]])   // move up: at or above the middle
    expect(at(place(two, 1, { y: 4 }))).toEqual([[0, 0], [0, 6]])
  })

  it('keeps a panel beside another where it fits, and clamps to the grid', () => {
    const out = place([box(0, 0, 12, 6), box(0, 6, 12, 6)], 1, { x: 30, y: 0 })
    expect(at(out)).toEqual([[0, 0], [12, 0]])
    const wide = place([box(0, 0, 12, 6)], 0, { w: 40 })
    expect(wide[0]).toMatchObject({ x: 0, w: 24 })
    for (const [a, b] of [[0, 1]]) expect(overlap(out[a], out[b])).toBe(false)
  })

  it('leaves panels alone that the moved one only passed', () => {
    // Hall left, notes and switches stacked right; notes dragged down-left, onto the hall's lower half.
    const out = place([box(0, 0, 16, 10), box(16, 0, 8, 4), box(16, 4, 8, 6)], 1, { x: 11, y: 6 })
    expect(at(out)).toEqual([[0, 0], [11, 10], [16, 0]])
  })

  it('adds a panel in the first gap', () => {
    expect(at(add([box(0, 0, 12, 6)], empty, 8, 6)).slice(-1)).toEqual([[12, 0]])
    expect(at(add([box(0, 0, 24, 6)], empty, 8, 6)).slice(-1)).toEqual([[0, 6]])
  })

  it('snaps page heights to small, medium and large, and goes free above large', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8, 11].map(snapHeight)).toEqual([3, 3, 3, 5, 5, 5, 8, 8, 11])
    expect([stepHeight(3, 1), stepHeight(5, 1), stepHeight(8, 1), stepHeight(4, 1)]).toEqual([5, 8, 9, 5])
    expect([stepHeight(9, -1), stepHeight(8, -1), stepHeight(5, -1), stepHeight(3, -1)]).toEqual([8, 5, 3, 3])
  })
})
