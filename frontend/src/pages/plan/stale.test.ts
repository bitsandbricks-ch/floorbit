import { describe, expect, it } from 'vitest'
import { STALE_AFTER_MS, staleFor } from './stale'

describe('telling when the plan is old', () => {
  it('is fresh until three answers are missed', () => {
    expect(staleFor(1000, 1000 + STALE_AFTER_MS - 1, false)).toBe(0)
    expect(staleFor(1000, 1000 + STALE_AFTER_MS, false)).toBe(STALE_AFTER_MS)
  })
  it('says so at once when the last ask failed', () => {
    expect(staleFor(1000, 31_000, true)).toBe(30_000)
  })
  it('says nothing before the first answer', () => {
    expect(staleFor(0, 999_999, true)).toBe(0)
  })
})
