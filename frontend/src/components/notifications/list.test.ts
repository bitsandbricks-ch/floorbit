import { describe, expect, it } from 'vitest'
import type { Problem, ProblemList } from '@/api/types'
import { countGroups, filterItems, notifyItems, pageOf, PER_PAGE } from './list'

const prob = (id: string, level: 'down' | 'warn', since: number, extra: Partial<Problem> = {}): Problem =>
  ({ id, kind: 'switch', level, title: `t-${id}`, where: `w-${id}`, since, link: '/', ...extra })

const data = (problems: Problem[], attention: Problem[] = []): ProblemList =>
  ({ problems, attention, counts: { down: 0, warn: 0, muted: 0 }, mutes: [], quiet_hours: false, checked_at: 0, can_mute: false })

describe('notifyItems', () => {
  it('puts down first, then warnings, then seats, newest first within down and warnings', () => {
    const items = notifyItems(data(
      [prob('w1', 'warn', 5), prob('d1', 'down', 1), prob('d2', 'down', 9), prob('w2', 'warn', 7)],
      [prob('s1', 'warn', 3, { kind: 'duplex', seat: 'A-1' })],
    ))
    expect(items.map((i) => i.p.id)).toEqual(['d2', 'd1', 'w2', 'w1', 's1'])
    expect(items.map((i) => i.group)).toEqual(['down', 'down', 'warn', 'warn', 'seats'])
  })

  it('leaves muted ones out, like the bell count', () => {
    const muted = { until: 9, by: null, reason: '' }
    expect(notifyItems(data([prob('d1', 'down', 1, { muted })], [prob('s1', 'warn', 1, { muted })]))).toEqual([])
  })
})

describe('filterItems', () => {
  const items = notifyItems(data(
    [prob('d1', 'down', 1, { title: 'sw-c-02: offline', device: 'sw-c-02' }), prob('w1', 'warn', 2, { title: 'Circuit B close' })],
    [prob('s1', 'warn', 3, { title: 'Seat A-6 duplex', seat: 'A-6' })],
  ))

  it('filters by group and counts each group', () => {
    expect(filterItems(items, 'seats', '').map((i) => i.p.id)).toEqual(['s1'])
    expect(countGroups(items)).toEqual({ all: 3, down: 1, warn: 1, seats: 1 })
  })

  it('searches title, place, device and seat, every word', () => {
    expect(filterItems(items, 'all', 'SW-C').map((i) => i.p.id)).toEqual(['d1'])
    expect(filterItems(items, 'all', 'seat a-6').map((i) => i.p.id)).toEqual(['s1'])
    expect(filterItems(items, 'down', 'circuit')).toEqual([])
  })
})

it('pages at 50: 120 items make 3 pages', () => {
  expect(PER_PAGE).toBe(50)
  expect(pageOf(0)).toBe(1)
  expect(pageOf(49)).toBe(1)
  expect(pageOf(50)).toBe(2)
  expect(pageOf(119)).toBe(3)
})
