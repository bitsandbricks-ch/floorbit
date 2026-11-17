import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import type { ItemRef } from './geometry'
import { similar } from './similar'

const data = {
  drawing: {
    shapes: [], box: '0 0 10 10', cell: 32,
    marks: [{ id: 'w1', kind: 'wall' }, { id: 'w2', kind: 'wall' }, { id: 't1', kind: 'text' }, { id: 'z1', kind: 'zone' }],
  },
} as unknown as SeatViewData
const items: ItemRef[] = [
  { kind: 'mark', id: 'w1' }, { kind: 'mark', id: 'w2' }, { kind: 'mark', id: 't1' }, { kind: 'mark', id: 'z1' },
  { kind: 'block', id: 'A' }, { kind: 'block', id: 'B' }, { kind: 'switch', id: 's1' }, { kind: 'cable', id: 'c1' },
]
const ids = (r: ItemRef[]) => r.map((x) => x.id)

describe('similar', () => {
  it('picks the same kind, and for marks the same sort', () => {
    expect(ids(similar(data, items, [{ kind: 'mark', id: 'w2' }]))).toEqual(['w1', 'w2'])
    expect(ids(similar(data, items, [{ kind: 'block', id: 'A' }]))).toEqual(['A', 'B'])
    expect(ids(similar(data, items, [{ kind: 'cable', id: 'c1' }]))).toEqual(['c1'])
  })

  it('takes every kind in a mixed selection', () => {
    expect(ids(similar(data, items, [{ kind: 'mark', id: 't1' }, { kind: 'switch', id: 's1' }]))).toEqual(['t1', 's1'])
    expect(similar(data, items, [])).toEqual([])
  })
})
