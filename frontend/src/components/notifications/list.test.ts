import { describe, expect, it } from 'vitest'
import type { Problem, ProblemList } from '@/api/types'
import { notifyItems } from './list'

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
    expect(items.map((i) => i.id)).toEqual(['d2', 'd1', 'w2', 'w1', 's1'])
    expect(items.map((i) => i.group)).toEqual(['down', 'down', 'warn', 'warn', 'seats'])
  })

  it('leaves muted ones out, like the bell count', () => {
    const muted = { until: 9, by: null, reason: '' }
    expect(notifyItems(data([prob('d1', 'down', 1, { muted })], [prob('s1', 'warn', 1, { muted })]))).toEqual([])
  })

  it('lets the search find the device and the seat too', () => {
    const [d, s] = notifyItems(data(
      [prob('d1', 'down', 1, { title: 'sw-c-02: offline', device: 'sw-c-02' })],
      [prob('s1', 'warn', 3, { title: 'Duplex mismatch', seat: 'A-6' })],
    ))
    expect(d.search).toContain('sw-c-02')
    expect(s.search).toContain('A-6')
  })
})
