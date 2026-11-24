import { describe, expect, it } from 'vitest'
import { draggedGap, gapSpots, keepTop, rowAt } from './rowGaps'
import { twoRows } from './rowGaps.fixtures'

describe('the space between rows', () => {
  it('puts a bar halfway between two rows, as wide as both', () => {
    expect(gapSpots(twoRows, 32)).toEqual([{ row: 1, y: 1.5, x1: 0, x2: 3 }])
  })

  it('keeps a dragged space within 0 and 20 seats, on quarter seats unless free', () => {
    expect(draggedGap(1, 0.6)).toBe(1.5)
    expect(draggedGap(1, 0.63, true)).toBe(1.63)
    expect(draggedGap(1, -3)).toBe(0)
    expect(draggedGap(19, 5)).toBe(20)
  })

  it('moves the block half the change so the rows above stay put, turned with the block', () => {
    expect(keepTop(twoRows, 32, { w: 1600, h: 1000 }, 1)).toEqual({ x: 12.5, y: 21.6 })
    expect(keepTop({ ...twoRows, rotation: 90 }, 32, { w: 1600, h: 1000 }, 1)).toEqual({ x: 11.5, y: 20 })
  })

  it('finds the row nearest a point', () => {
    expect(rowAt(twoRows, 32, [1.5, 2.6])).toBe(1)
    expect(rowAt(twoRows, 32, [0.2, 0.4])).toBe(0)
  })
})
