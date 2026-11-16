import { describe, expect, it } from 'vitest'
import { cleanGaps, freeGapSpot } from './gaps'

describe('gaps in a seat block', () => {
  it('keeps one gap per place, inside the block, sorted', () => {
    expect(cleanGaps([{ after: 6, size: 1 }, { after: 2, size: 30 }, { after: 8, size: 1 }, { after: 6, size: 2 }], 8))
      .toEqual([{ after: 2, size: 20 }, { after: 6, size: 2 }])
  })

  it('puts a new gap in the middle, then the nearest free place', () => {
    expect(freeGapSpot([], 8)).toBe(4)
    expect(freeGapSpot([{ after: 4, size: 1 }], 8)).toBe(3)
    expect(freeGapSpot([], 1)).toBeNull()
  })
})
