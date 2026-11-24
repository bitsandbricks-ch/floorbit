import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { aRow, drawnBlock } from './rowGaps.fixtures'
import type { BlockRow } from './rows'
import { RowShapeHandles } from './RowShapeHandles'
import { armEnds, blockSeats, mirrorBlock, rowSeats } from './rowShapes'

const round = (ps: [number, number][]) => ps.map(([x, y]) => [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000])

describe('rows turned over like the server (floorbit/seat_rows.py)', () => {
  // The expected places are what seat_rows.row_seats gives for the same rows.
  it.each([
    ['mirrored L', { seats: 4, shape: 'l', sides: [2, 2], mirror: true }, [[-0.5, 0.5], [-0.5, 1.5], [-1.5, 2.5], [-2.5, 2.5]]],
    ['flipped U', { seats: 8, shape: 'u', sides: [2, 4, 2], flip: true }, [[0.5, -0.5], [0.5, -1.5], [1.5, -2.5], [2.5, -2.5], [3.5, -2.5], [4.5, -2.5], [5.5, -1.5], [5.5, -0.5]]],
    ['arc turned half round', { shape: 'arc', bend: 90, mirror: true, flip: true }, [[-0.38, 0.324], [-1.267, 0.777], [-2.251, 0.932], [-3.234, 0.777], [-4.122, 0.324]]],
    ['mirrored path', { seats: 4, shape: 'path', path: [[0, 0], [2, 0], [2, 2]], mirror: true }, [[-0.5, 0], [-1.5, 0], [-2, 0.5], [-2, 1.5]]],
  ] as const)('%s', (_, extra, want) => {
    expect(round(rowSeats(aRow(extra as Partial<BlockRow>)))).toEqual(want)
  })

  it('grows a mirrored L arm the mirrored way', () => {
    const ends = armEnds(aRow({ seats: 4, shape: 'l', sides: [2, 2], mirror: true }))
    expect(ends.map((e) => e.grow.map((v) => v + 0))).toEqual([[0, -1], [-1, 0]])
  })
})

describe('mirroring a whole block', () => {
  it('turns every row over and lines them up from the other end, in the same box', () => {
    const rows = [aRow({ seats: 6 }), aRow({ id: '2', seats: 3, shape: 'l', sides: [1, 2], align: 'start', shift: 1 })]
    const out = mirrorBlock({ rows })
    expect(out.rows.map((r) => [r.mirror, r.align, r.shift])).toEqual([[true, 'end', -0], [true, 'end', -1]])
    const was = blockSeats(rows), now = blockSeats(out.rows)
    expect([now.w, now.h]).toEqual([was.w, was.h])
    // Every seat lands across the middle from where it was.
    expect(now.at.map((row) => round(row))).toEqual(was.at.map((row) => round(row.map(([x, y]) => [was.w - x, y] as [number, number]))))
  })

  it('moves seats placed by hand across too', () => {
    const out = mirrorBlock({ rows: [aRow({ seats: 2 })], seat_at: { '1,0': [0, 0], '1,1': [3, 1] } })
    expect(out.seat_at).toEqual({ '1,0': [3, 0], '1,1': [0, 1] })
  })
})

describe('handles on a mirrored path', () => {
  it('drags a point the way the pointer goes', () => {
    const row = aRow({ seats: 5, shape: 'path', path: [[0, 0], [3, 0], [3, 2]], mirror: true })
    const onDone = vi.fn()
    const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }
    const { container } = renderWithApp(<svg><RowShapeHandles ctx={ctx} shape={drawnBlock([row])} cell={32} size={{ w: 1600, h: 1000 }} rows={[row]} r={0} onDone={onDone} /></svg>)
    const pt = container.querySelector('[data-point="1"]')!
    // The point at the turn stands on the left now, level with the first seats.
    const x = Number(pt.getAttribute('cx')), y = Number(pt.getAttribute('cy'))
    expect(x).toBeLessThan(Number(container.querySelector('[data-point="0"]')!.getAttribute('cx')))
    fireEvent.pointerDown(pt, { button: 0, pointerId: 1, clientX: x, clientY: y })
    fireEvent.pointerMove(pt, { pointerId: 1, clientX: x - 32, clientY: y })
    fireEvent.pointerUp(pt, { pointerId: 1, clientX: x - 32, clientY: y })
    // A seat further left on the plan is a seat further along in the row's own (unmirrored) frame.
    expect(onDone).toHaveBeenCalledWith({ ...row, path: [[0, 0], [4, 0], [3, 2]] }, expect.any(Object))
  })
})
