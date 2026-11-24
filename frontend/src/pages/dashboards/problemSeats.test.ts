import { describe, expect, it } from 'vitest'
import { problemSeats } from './problemSeats'

describe('problemSeats', () => {
  it('lists only the area\'s seats with problems, most first, then by number', () => {
    const seats = {
      'A-10': { state: 'offline' as const, problems: 1 },
      'A-2': { state: 'offline' as const, problems: 1 },
      'A-3': { state: 'online' as const, problems: 2 },
      'A-4': { state: 'online' as const },
      'B-1': { state: 'offline' as const, problems: 3 },
    }
    expect(problemSeats(seats, new Set(['A-10', 'A-2', 'A-3', 'A-4'])).map((s) => s.seat)).toEqual(['A-3', 'A-2', 'A-10'])
  })
})
