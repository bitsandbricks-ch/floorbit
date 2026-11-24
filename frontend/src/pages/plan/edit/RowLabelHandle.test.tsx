import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { aRow, drawnBlock } from './rowGaps.fixtures'
import { RowLabelHandle } from './RowLabelHandle'

const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }

describe('RowLabelHandle', () => {
  it('moves the letter in the row frame, half a seat at a time', () => {
    const row = aRow({ seats: 4 })
    const shape = { ...drawnBlock([row]), rows: [{ text: 'K', r: 0, x: -64 - 16, y: 0 }] }
    const onDone = vi.fn()
    const { getByRole } = renderWithApp(<svg><RowLabelHandle ctx={ctx} shape={shape} cell={32} row={row} r={0} onDone={onDone} /></svg>)
    const h = getByRole('button', { name: 'Move the letter of row 1' })
    const x = Number(h.getAttribute('cx')), y = Number(h.getAttribute('cy'))
    fireEvent.pointerDown(h, { button: 0, pointerId: 1, clientX: x, clientY: y })
    fireEvent.pointerMove(h, { pointerId: 1, clientX: x + 10, clientY: y - 48 })
    fireEvent.pointerUp(h, { pointerId: 1, clientX: x + 10, clientY: y - 48 })
    // From -0.5 seats (one before seat 1's centre) it goes a third of a seat right (snapped back) and a seat and a half up, a seat above the seat centres.
    expect(onDone).toHaveBeenCalledWith({ ...row, label: 'moved', label_at: [0, -1] })
  })

  it('shows nothing for a row without a letter', () => {
    const row = aRow({ seats: 4 })
    const { container } = renderWithApp(<svg><RowLabelHandle ctx={ctx} shape={drawnBlock([row])} cell={32} row={row} r={0} onDone={vi.fn()} /></svg>)
    expect(container.querySelector('[data-handle="row-label"]')).toBeNull()
  })
})
