import { describe, expect, it } from 'vitest'
import type { Problem } from '@/api/types'
import { fold, GROUP_FROM } from './fold'

const seat = (n: number, since: number): Problem => ({
  id: `checkin:s1:Gi1/0/${n}`, kind: 'checkin', level: 'warn', title: `Seat A-${n} is online without a check-in`,
  where: `sw-a-01 Gi1/0/${n} (seat A-${n})`, since, link: '/plan?seat=A-' + n, seat: `A-${n}`, priority: 3,
})
const fw: Problem = { id: 'switch:fw3', kind: 'switch', level: 'down', title: 'fw-03 is offline', where: 'fw-03', since: 50,
  link: '', name: 'fw-03', switch_id: 'fw3', priority: 1 }
const link: Problem = { id: 'link:l1', kind: 'link', level: 'down', title: 'Link core-01 Eth1/3 to fw-03 Port1 is down', where: '',
  since: null, link: '', ends: ['core-01', 'FW-03'] }

describe('fold (issue #1415)', () => {
  it('makes one row of the same seat problem on many seats, from the first one seen', () => {
    const rows = fold([fw, ...Array.from({ length: GROUP_FROM + 1 }, (_, i) => seat(i + 1, 100 + i))])
    expect(rows.map((r) => r.id)).toEqual(['switch:fw3', 'group:checkin:warn'])
    expect(rows[1]!.members).toHaveLength(GROUP_FROM + 1)
    expect(rows[1]!.since).toBe(100)
  })

  it('keeps a few, and a kind picked on purpose, one row each', () => {
    expect(fold([seat(1, 1), seat(2, 2)]).map((r) => r.id)).toHaveLength(2)
    expect(fold([seat(1, 1), seat(2, 2), seat(3, 3)], (k) => k === 'checkin')).toHaveLength(3)
  })

  it('keeps seat problems that say something of their own one row each', () => {
    const logs = [1, 2, 3].map((n) => ({ ...seat(n, n), id: `log:${n}`, kind: 'log' as const, title: `Line ${n}` }))
    expect(fold(logs)).toHaveLength(3)
  })

  it('hangs a down link under the down box at either end', () => {
    const rows = fold([fw, link])
    expect(rows.map((r) => r.id)).toEqual(['switch:fw3'])
    expect(rows[0]!.links?.map((l) => l.id)).toEqual(['link:l1'])
  })

  it('leaves a link alone when neither end is on the list', () => {
    expect(fold([link]).map((r) => r.id)).toEqual(['link:l1'])
  })
})
