import { describe, expect, it } from 'vitest'
import type { BlockRow } from './rows'
import { aRow, drawnBlock } from './rowGaps.fixtures'
import { addPoint, armEnds, bendThrough, drawnSeats, dropPoint, movePoint, reshaped, rowOffset, rowSeats, withArm } from './rowShapes'

const row = aRow
const round = (ps: [number, number][]) => ps.map(([x, y]) => [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000])

describe('rows laid out like the server (floorbit/seat_rows.py)', () => {
  // The expected places are what seat_rows.row_seats gives for the same rows.
  it.each([
    ['arc', { shape: 'arc', bend: 90 }, [[0.38, -0.324], [1.267, -0.777], [2.251, -0.932], [3.234, -0.777], [4.122, -0.324]]],
    ['U', { shape: 'u', sides: [1, 3, 1] }, [[0.5, 0.5], [1.5, 1.5], [2.5, 1.5], [3.5, 1.5], [4.5, 0.5]]],
    ['L', { shape: 'l', sides: [2, 3] }, [[0.5, 0.5], [0.5, 1.5], [1.5, 2.5], [2.5, 2.5], [3.5, 2.5]]],
    ['path', { shape: 'path', path: [[0, 0], [2, 0], [2, 3]] }, [[0.5, 0], [1.5, 0], [2, 0.5], [2, 1.5], [2, 2.5]]],
    ['line with a gap', { col_gaps: [{ after: 2, size: 1 }] }, [[0.5, 0.5], [1.5, 0.5], [3.5, 0.5], [4.5, 0.5], [5.5, 0.5]]],
  ] as const)('%s', (_, extra, want) => {
    expect(round(rowSeats(row(extra as Partial<BlockRow>)))).toEqual(want)
  })
})

describe('shaping a row on the plan', () => {
  it('bends an arc through the dragged point, to the left of the way the row runs when positive', () => {
    expect(bendThrough([0, 0], [10, 0], [5, -2])).toBe(85)    // 4·atan(0.4) ≈ 87.2°, on 5° steps
    expect(bendThrough([0, 0], [10, 0], [5, 2])).toBe(-85)
    expect(bendThrough([0, 0], [10, 0], [5, -2], true)).toBe(87)
    expect(bendThrough([0, 0], [10, 0], [5, -500])).toBe(330)
  })

  it('makes an arm longer with seats from the middle (U) or the other arm (L), keeping the count', () => {
    expect(withArm(row({ shape: 'u', seats: 6, sides: [1, 4, 1] }), 0, 2).sides).toEqual([3, 2, 1])
    expect(withArm(row({ shape: 'u', seats: 6, sides: [1, 4, 1] }), 2, 9).sides).toEqual([1, 0, 5])
    expect(withArm(row({ shape: 'l', seats: 6, sides: [3, 3] }), 1, -1).sides).toEqual([4, 2])
    expect(armEnds(row({ shape: 'l', sides: [2, 3] }))).toEqual([{ arm: 0, at: [0.5, 0.5], grow: [0, -1] }, { arm: 1, at: [3.5, 2.5], grow: [1, 0] }])
  })

  it('moves, adds and takes out path points', () => {
    const path: [number, number][] = [[0, 0], [4, 0], [4, 4]]
    expect(movePoint(path, 1, [5.13, 0.4])).toEqual([[0, 0], [5.25, 0.5], [4, 4]])
    expect(addPoint(path, 0)).toEqual([[0, 0], [2, 0], [4, 0], [4, 4]])
    expect(dropPoint(path, 1)).toEqual([[0, 0], [4, 4]])
    expect(dropPoint([[0, 0], [4, 0]], 0)).toEqual([[0, 0], [4, 0]])
  })

  it('finds the row frame from the drawn seats', () => {
    expect(rowOffset(row({}), [[3, 7]])).toEqual([2.5, 6.5])
  })

  // The anchor seat's place on the plan: the block's middle (from x/y in %) plus its place from the middle.
  const size = { w: 1600, h: 1000 }
  const onPlan = (rows: BlockRow[], x: number, y: number, r: number, c: number) => {
    const shape = drawnBlock(rows, (x / 100) * size.w, (y / 100) * size.h)
    const p = drawnSeats(shape, 32, r)[c]
    return [Math.round((shape.cx - shape.w / 2 + p[0] * 32) * 100) / 100, Math.round((shape.cy - shape.h / 2 + p[1] * 32) * 100) / 100]
  }
  it.each([
    ['a path gets a new leg (the first seat stays)', [aRow({ shape: 'path', path: [[0, 0], [3, 0]] })], 0, aRow({ shape: 'path', path: [[0, 0], [3, 0], [3, 4]] }), 0, 0],
    ['an arc bends (the first seat stays)', [aRow({}), aRow({ id: '2', shape: 'arc', bend: 0 })], 1, aRow({ id: '2', shape: 'arc', bend: 120 }), 0, 0],
    ['a U arm grows (the middle stays)', [aRow({}), aRow({ id: '2', seats: 8, shape: 'u', sides: [2, 4, 2] })], 1, aRow({ id: '2', seats: 8, shape: 'u', sides: [4, 2, 2] }), 2, 4],
  ] as const)('keeps the block in place when %s', (_, rows, r, next, before, after) => {
    const shape = drawnBlock([...rows], 400, 300)
    const out = reshaped(shape, 32, size, [...rows], r, next)
    const nextRows = rows.map((x, k) => (k === r ? next : x))
    expect(onPlan(nextRows, out.x, out.y, r, after)).toEqual(onPlan([...rows], 25, 30, r, before))
    // The preview puts the anchor seat on its old place in the block as drawn now.
    expect(out.seats[after]).toEqual(drawnSeats(shape, 32, r)[before])
  })
})
