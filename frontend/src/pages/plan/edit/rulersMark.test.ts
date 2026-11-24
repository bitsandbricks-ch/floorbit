import { describe, expect, it } from 'vitest'
import { seatsLabel } from './rulers'

describe('seatsLabel', () => {
  it('reads a plan position in seats, one decimal at most', () => {
    expect(seatsLabel(320, 32)).toBe('10')
    expect(seatsLabel(1811, 32)).toBe('56.6')
    expect(seatsLabel(-48, 32)).toBe('-1.5')
  })
})
