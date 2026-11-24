import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlanShape } from '@/api/types'
import { renderWithApp } from '@/test/render'
import type { BlockRow } from './rows'
import { RowShapeHandles } from './RowShapeHandles'

const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }
// One row of five seats along a path: three to the right, then two down. 32 units a seat, the
// block's middle at 200,200; in the block's frame the seats sit half a seat lower than the path.
const row: BlockRow = { id: '1', seats: 5, shape: 'path', path: [[0, 0], [3, 0], [3, 2]], gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [] }
const centres: [number, number][] = [[0.5, 0.5], [1.5, 0.5], [2.5, 0.5], [3, 1], [3, 2]]
const shape: PlanShape = {
  id: 'b1', cx: 200, cy: 200, rotation: 0, w: 112, h: 80, name: 'A', row_list: [{ id: 'b1:1', name: 'A', row: '1' }],
  cells: centres.map(([x, y], c) => ({ x: (x - 0.5) * 32 - 56, y: (y - 0.5) * 32 - 40, seat: `A-${c + 1}`, hit: false, on: null, rc: [0, c] as [number, number] })),
}

function handles() {
  const onDone = vi.fn()
  const r = renderWithApp(<svg><RowShapeHandles ctx={ctx} shape={shape} cell={32} size={{ w: 1600, h: 1000 }} rows={[row]} r={0} onDone={onDone} /></svg>)
  return { ...r, onDone, q: (sel: string) => r.container.querySelector(sel)! }
}

describe('Row shape handles', () => {
  it('puts a handle on every point of the path, where the seats follow it', () => {
    const { container, q } = handles()
    expect(container.querySelectorAll('[data-handle="point"]')).toHaveLength(3)
    expect(q('[data-point="1"]')).toHaveAttribute('cx', '240')   // 200 - 56 + 3 × 32
    expect(q('[data-point="1"]')).toHaveAttribute('cy', '176')   // 200 - 40 + 0.5 × 32
  })

  it('drags a point to a new place, on quarter seats', () => {
    const { q, onDone } = handles()
    const pt = q('[data-point="1"]')
    fireEvent.pointerDown(pt, { button: 0, pointerId: 1, clientX: 240, clientY: 176 })
    fireEvent.pointerMove(pt, { pointerId: 1, clientX: 270, clientY: 177 })
    fireEvent.pointerUp(pt, { pointerId: 1, clientX: 273, clientY: 177 })
    expect(onDone).toHaveBeenCalledWith({ ...row, path: [[0, 0], [4, 0], [3, 2]] }, expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }))
  })

  it('adds a point halfway along a leg, and a double click takes one out', () => {
    const { q, onDone } = handles()
    fireEvent.pointerDown(q('[data-handle="add-point"][data-leg="0"]'), { button: 0, pointerId: 1 })
    expect(onDone).toHaveBeenLastCalledWith({ ...row, path: [[0, 0], [1.5, 0], [3, 0], [3, 2]] }, { x: 12.5, y: 20 })
    fireEvent.doubleClick(q('[data-point="0"]'))
    expect(onDone).toHaveBeenLastCalledWith({ ...row, path: [[3, 0], [3, 2]] }, expect.any(Object))
  })
})
