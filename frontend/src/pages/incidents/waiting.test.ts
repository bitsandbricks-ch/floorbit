import { describe, expect, it } from 'vitest'
import { isWaiting, nextToTake } from './waiting'

const now = 1_763_200_000
const open = { status: 'open' as const, assignee: null, can_work: true }

describe('waiting', () => {
  it('stops waiting once the seat says it works again (issue #376)', () => {
    expect(isWaiting({ ...open, created_at: now - 20 * 60 }, now)).toBe(true)
    expect(isWaiting({ ...open, created_at: now - 20 * 60, seat_ok_at: now - 60 }, now)).toBe(false)
  })

  it('takes the ones the seat called off last', () => {
    const items = [
      { ...open, id: 'old-ok', created_at: now - 30 * 60, seat_ok_at: now - 60 },
      { ...open, id: 'newer', created_at: now - 5 * 60 },
      { ...open, id: 'newest', created_at: now - 60 },
    ]
    expect(nextToTake(items)?.id).toBe('newer')
    expect(nextToTake([items[0]])?.id).toBe('old-ok')
  })
})
