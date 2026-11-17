import { describe, expect, it } from 'vitest'
import { blockTop } from './blockTop'

describe('blockTop', () => {
  it('puts a long row’s name just above it, not half its width away', () => {
    expect(blockTop({ cx: 400, cy: 400, w: 400, h: 64, rotation: 0 })).toBe(400 - 32 - 6)
  })
  it('uses the width once the block stands upright', () => {
    expect(blockTop({ cx: 400, cy: 400, w: 400, h: 64, rotation: 90 })).toBeCloseTo(400 - 200 - 6)
  })
})
