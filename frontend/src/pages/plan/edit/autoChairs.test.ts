import { describe, expect, it } from 'vitest'
import { autoChairs, sideFor, withCables } from './autoChairs'
import { aRow } from './rowGaps.fixtures'

const sides = (rows: ReturnType<typeof aRow>[]) => autoChairs(rows).map((r) => r.side)

describe('autoChairs', () => {
  it('puts the chairs of rows sharing a table on its outer sides', () => {
    // Two pairs: touching, and with a small cable gap; an aisle between them.
    const rows = [aRow({ id: '1' }), aRow({ id: '2', gap: 0.5 }), aRow({ id: '3', gap: 3 }), aRow({ id: '4' })]
    expect(sides(rows)).toEqual(['left', 'right', 'left', 'right'])
  })

  it('turns a row on its own to its bigger gap, the block edge counting as open floor', () => {
    const rows = [aRow({ id: '1' }), aRow({ id: '2' }), aRow({ id: '3', gap: 3 })]
    expect(sides(rows)).toEqual(['left', 'right', 'right'])
    // Alone in its block, both sides are open: the row keeps what it has.
    expect(sides([aRow({ id: '1', side: 'right' })])).toEqual(['right'])
  })

  it('leaves bent rows alone and keeps the middle of three', () => {
    const rows = [aRow({ id: '1' }), aRow({ id: '2', side: 'right' }), aRow({ id: '3' }), aRow({ id: '4', shape: 'u', seats: 8, gap: 3 })]
    expect(sides(rows)).toEqual(['left', 'right', 'right', ''])
  })

  it('stores the other side on a flipped row, so the chairs still land where they should', () => {
    expect(sideFor(aRow({ flip: true }), 'above')).toBe('right')
    expect(sideFor(aRow({ mirror: true }), 'above')).toBe('left')
  })
})

describe('withCables', () => {
  it('sets every row, and Auto leaves the field out', () => {
    const rows = withCables([aRow({ id: '1' }), aRow({ id: '2', cables: 'chair' })], 'behind')
    expect(rows.map((r) => r.cables)).toEqual(['behind', 'behind'])
    expect(withCables(rows, '').every((r) => !('cables' in r))).toBe(true)
  })
})
