import { describe, expect, it } from 'vitest'
import { type BlockRow, withUSide } from './rows'

const u = (sides: number[], seats = 12): BlockRow =>
  ({ id: '1', seats, shape: 'u', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [], sides }) as BlockRow

describe('withUSide', () => {
  it('works out the middle from the two sides', () => {
    expect(withUSide(u([3, 6, 3]), 0, 4).sides).toEqual([4, 5, 3])
    expect(withUSide(u([3, 6, 3]), 2, 1).sides).toEqual([3, 8, 1])
  })
  it('never lets a side take more than the other side leaves', () => {
    expect(withUSide(u([3, 6, 3]), 0, 20).sides).toEqual([9, 0, 3])
  })
})
