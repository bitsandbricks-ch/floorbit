import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import { RowGapHandles } from './RowGapHandles'
import { twoRows } from './rowGaps.fixtures'

const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }

function handles(picked: number | null = null) {
  const onDone = vi.fn(), onPick = vi.fn()
  const r = renderWithApp(<svg><RowGapHandles ctx={ctx} shape={twoRows} cell={32} gaps={[0, 1]} picked={picked} onPick={onPick} onDone={onDone} /></svg>)
  return { ...r, onDone, onPick, bar: r.container.querySelector('[data-handle="row-gap"]')! }
}

describe('Row gap handles', () => {
  it('drags the space above row B a seat bigger', () => {
    const { bar, onDone, container } = handles()
    expect(bar).toHaveAttribute('aria-label', 'Drag to change the space above B')
    fireEvent.pointerDown(bar, { button: 0, pointerId: 1, clientX: 200, clientY: 200 })
    fireEvent.pointerMove(bar, { pointerId: 1, clientX: 200, clientY: 233 })
    expect(container.querySelector('.fb-row-gap-label')).toHaveTextContent('2 seats')
    fireEvent.pointerUp(bar, { pointerId: 1, clientX: 200, clientY: 233 })
    expect(onDone).toHaveBeenCalledWith(1, 2)
  })

  it('picks the row under a bar on a click', () => {
    const { bar, onDone, onPick } = handles()
    fireEvent.pointerDown(bar, { button: 0, pointerId: 1, clientX: 200, clientY: 200 })
    fireEvent.pointerUp(bar, { pointerId: 1, clientX: 200, clientY: 200 })
    expect(onPick).toHaveBeenCalledWith(1)
    expect(onDone).not.toHaveBeenCalled()
  })

  it('outlines the picked row', () => {
    expect(handles(0).container.querySelector('.fb-row-picked')).toHaveAttribute('data-picked-row', '0')
  })
})
