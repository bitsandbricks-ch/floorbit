import { describe, expect, it } from 'vitest'
import { blockAlarm, blockTop } from './blockTop'

describe('blockTop', () => {
  it('puts a long row’s name just above it, not half its width away', () => {
    expect(blockTop({ cx: 400, cy: 400, w: 400, h: 64, rotation: 0 })).toBe(400 - 32 - 6)
  })
  it('uses the width once the block stands upright', () => {
    expect(blockTop({ cx: 400, cy: 400, w: 400, h: 64, rotation: 90 })).toBeCloseTo(400 - 200 - 6)
  })
})

describe('blockAlarm', () => {
  it('marks a block from a quarter of its seats with problems, two at least', () => {
    expect(blockAlarm({ seats: 24, problems: 6 })).toBe(true)
    expect(blockAlarm({ seats: 24, problems: 5 })).toBe(false)
    expect(blockAlarm({ seats: 4, problems: 1 })).toBe(false)
    expect(blockAlarm({ seats: 4, problems: 2 })).toBe(true)
    expect(blockAlarm(undefined)).toBe(false)
  })
})
