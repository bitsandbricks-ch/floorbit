import { describe, expect, it } from 'vitest'
import { isSnoozed, isWaiting, nextToTake, openOrder } from './waiting'

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

  it('puts snoozed ones aside until the snooze ends (issue #887)', () => {
    const aside = { ...open, id: 'aside', created_at: now - 30 * 60, snoozed_until: now + 600 }
    const other = { ...open, id: 'other', created_at: now - 60 }
    expect(isSnoozed(aside, now)).toBe(true)
    expect(isWaiting(aside, now)).toBe(false)
    expect(isWaiting(aside, now + 601)).toBe(true)
    expect(openOrder([aside, other], now).map((i) => i.id)).toEqual(['other', 'aside'])
    expect(nextToTake([aside, other], now)?.id).toBe('other')
    expect(isSnoozed({ ...aside, status: 'fixed' as const }, now)).toBe(false)
  })
})
