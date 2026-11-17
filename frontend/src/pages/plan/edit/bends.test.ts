import { describe, expect, it } from 'vitest'
import { addBend, bendsPct, midpoints, moveBend, removeBend, snapBend } from './bends'

const route = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 50 }]

describe('cable bends', () => {
  it('offers the middle of each stretch', () => {
    expect(midpoints(route)).toEqual([{ x: 50, y: 0 }, { x: 100, y: 25 }])
  })

  it('moves, adds and removes bends but never the ends', () => {
    expect(moveBend(route, 0, { x: 80, y: 10 })[1]).toEqual({ x: 80, y: 10 })
    expect(addBend(route, 1, { x: 120, y: 25 })).toEqual([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 120, y: 25 }, { x: 100, y: 50 }])
    expect(removeBend(route, 0)).toEqual([{ x: 0, y: 0 }, { x: 100, y: 50 }])
  })

  it('snaps to half a cell unless free', () => {
    expect(snapBend({ x: 21, y: 9 }, 32, false)).toEqual({ x: 16, y: 16 })
    expect(snapBend({ x: 21, y: 9 }, 32, true)).toEqual({ x: 21, y: 9 })
  })

  it('keeps only the bends, in percent', () => {
    expect(bendsPct(route, { w: 1600, h: 1000 })).toEqual([[6.25, 0]])
  })
})
