import { describe, expect, it } from 'vitest'
import type { PlanShape } from '@/api/types'
import { fromBlock, moveSeat, seatPlaces, toBlock } from './seatPlace'

const CELL = 32
// Two seats side by side, the block's middle at (800, 500) on a 1600 x 1000 plan.
const shape: PlanShape = {
  id: 'b', cx: 800, cy: 500, rotation: 0, w: 2 * CELL, h: CELL, name: 'ADM',
  cells: [
    { x: -CELL, y: -CELL / 2, seat: 'ADM-1', hit: false, on: null, rc: [0, 0] },
    { x: 0, y: -CELL / 2, seat: 'ADM-2', hit: false, on: null, rc: [0, 1] },
  ],
}

describe('seats placed freely', () => {
  it('reads where the seats are and moves one, keeping the others on the plan', () => {
    expect(seatPlaces(shape, CELL)).toEqual({ '0,0': [0, 0], '0,1': [1, 0] })
    // Seat 2 goes under seat 1: the box is one seat wide and two high, its middle half a seat left and down.
    const moved = moveSeat(shape, CELL, { w: 1600, h: 1000 }, [0, 1], [0, 1])
    expect(moved.seat_at).toEqual({ '0,0': [0, 0], '0,1': [0, 1] })
    expect(moved.x).toBeCloseTo(((800 - CELL / 2) / 1600) * 100)
    expect(moved.y).toBeCloseTo(((500 + CELL / 2) / 1000) * 100)
    // Seat 1 out to the left: the places start at 0,0 again.
    expect(moveSeat(shape, CELL, { w: 1600, h: 1000 }, [0, 0], [-2, 0]).seat_at).toEqual({ '0,0': [0, 0], '0,1': [3, 0] })
  })

  it('turns plan points into the block frame and back, for a turned block too', () => {
    const turned = { ...shape, rotation: 90 }
    const p = fromBlock(turned, CELL, [0.5, 0.5])
    // Seat 1's middle sits half a seat left of the block's middle; turned a quarter, that is above it.
    expect(p.x).toBeCloseTo(800)
    expect(p.y).toBeCloseTo(500 - CELL / 2)
    expect(toBlock(turned, CELL, p)[0]).toBeCloseTo(0.5)
    expect(toBlock(turned, CELL, p)[1]).toBeCloseTo(0.5)
  })
})
