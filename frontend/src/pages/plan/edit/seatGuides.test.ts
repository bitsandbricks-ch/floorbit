import { describe, expect, it } from 'vitest'
import { alignSeats } from './seatGuides'

describe('alignSeats', () => {
  it('snaps a seat that comes close to another seat\'s column and shows the guide', () => {
    const { by, guides } = alignSeats([[0, 0]], [[3, 5], [8, 2]], [3.2, 1])
    expect(by).toEqual([3, 1])
    expect(guides).toEqual([{ x: 3.5, from: 1.5, to: 5.5 }])
  })

  it('lines up both ways at once, and leaves a seat far from any others alone', () => {
    expect(alignSeats([[0, 0]], [[3, 5], [8, 2]], [7.9, 2.1]).by).toEqual([8, 2])
    expect(alignSeats([[0, 0]], [[3, 5]], [1, 1])).toEqual({ by: [1, 1], guides: [] })
  })

  it('moves a whole selection by the nearest match', () => {
    const { by } = alignSeats([[0, 0], [1, 0]], [[5.1, 4]], [4, 3.9])
    expect(by[0]).toBeCloseTo(4.1)
    expect(by[1]).toBeCloseTo(4)
  })
})
