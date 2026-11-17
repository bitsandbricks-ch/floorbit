import { describe, expect, it } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { sharedEdits, sharedFields } from './shared'

const data = {
  drawing: {
    shapes: [{ id: 'a', rotation: 90 }],
    marks: [
      { id: 'w1', kind: 'wall', layer: 'safety' }, { id: 'w2', kind: 'wall', style: 'dashed', layer: 'safety' },
      { id: 'z', kind: 'zone', color: 'bit' }, { id: 't', kind: 'text', size: 'l', scale: 2, rotation: 90 }, { id: 'i', kind: 'icon' },
    ],
  },
} as unknown as SeatViewData

describe('editing several selected items at once', () => {
  it('offers the fields they all have, with the value when they agree', () => {
    expect(sharedFields(data, [{ kind: 'mark', id: 'w1' }, { kind: 'mark', id: 'w2' }])).toEqual({ layer: 'safety', style: null })
    expect(sharedFields(data, [{ kind: 'mark', id: 't' }, { kind: 'mark', id: 'i' }])).toEqual({ layer: 'overview', size: null, rotation: null })
    expect(sharedFields(data, [{ kind: 'block', id: 'a' }, { kind: 'mark', id: 't' }])).toEqual({ rotation: 90 })
    expect(sharedFields(data, [{ kind: 'mark', id: 'z' }])).toEqual({})
    expect(sharedFields(data, [{ kind: 'mark', id: 'z' }, { kind: 'switch', id: 's' }])).toEqual({})
  })
  it('changes only the items not at that value already, keeping what each had to undo', () => {
    expect(sharedEdits(data, [{ kind: 'mark', id: 'w1' }, { kind: 'mark', id: 'w2' }], 'style', 'dashed'))
      .toEqual([[{ kind: 'mark', id: 'w1' }, { style: 'solid' }, { style: 'dashed' }]])
    expect(sharedEdits(data, [{ kind: 'mark', id: 't' }, { kind: 'mark', id: 'i' }], 'size', 'l'))
      .toEqual([[{ kind: 'mark', id: 't' }, { size: 'l', scale: 2 }, { size: 'l', scale: 1 }], [{ kind: 'mark', id: 'i' }, { size: 'm', scale: 1 }, { size: 'l', scale: 1 }]])
    expect(sharedEdits(data, [{ kind: 'block', id: 'a' }, { kind: 'mark', id: 'w1' }], 'rotation', 0))
      .toEqual([[{ kind: 'block', id: 'a' }, { rotation: 90 }, { rotation: 0 }]])
  })
})
