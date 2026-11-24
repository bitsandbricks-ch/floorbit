import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlanShape } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { SeatHandles } from './SeatHandles'

const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }
// Three seats in a row (top-left corners at 0, 1, 2) and one a seat and a half below seat 1's left.
const places: [number, number][] = [[0, 0], [1, 0], [2, 0], [4.2, 2]]
const shape: PlanShape = {
  id: 'b', cx: 200, cy: 200, rotation: 0, w: 6 * 32, h: 3 * 32, name: 'A', free: true,
  cells: places.map(([x, y], c) => ({ x: x * 32 - 96, y: y * 32 - 48, seat: `A-${c + 1}`, hit: false, on: null, rc: [0, c] as [number, number] })),
}

function setup() {
  const onDone = vi.fn()
  const view = renderWithApp(<svg><SeatHandles ctx={ctx} shape={shape} cell={32} onDone={onDone} /></svg>)
  const seat = (n: number) => view.getByRole('button', { name: `Seat A-${n}: drag to move, Shift-click to pick more` })
  const drag = (el: Element, dx: number, dy: number, opts: object = {}) => {
    const x = Number(el.getAttribute('x')) + 16, y = Number(el.getAttribute('y')) + 16
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: x, clientY: y, ...opts })
    fireEvent.pointerMove(el, { pointerId: 1, clientX: x + dx, clientY: y + dy })
    fireEvent.pointerUp(el, { pointerId: 1, clientX: x + dx, clientY: y + dy })
  }
  return { ...view, onDone, seat, drag }
}

describe('SeatHandles', () => {
  it('moves the picked seats together', () => {
    const { seat, drag, onDone } = setup()
    fireEvent.pointerDown(seat(1), { button: 0, pointerId: 1, shiftKey: true })
    fireEvent.pointerDown(seat(2), { button: 0, pointerId: 1, shiftKey: true })
    expect(seat(1).getAttribute('aria-pressed')).toBe('true')
    drag(seat(2), 0, 32)
    expect(onDone).toHaveBeenCalledWith([{ rc: [0, 0], to: [0, 1] }, { rc: [0, 1], to: [1, 1] }])
  })

  it('lines a seat up with another one close by', () => {
    const { seat, drag, onDone } = setup()
    // Seat 3 dragged two seats down, a little short of seat 4's row and column: it snaps onto both lines.
    drag(seat(3), 2 * 32 + 6, 2 * 32 - 4)
    expect(onDone).toHaveBeenCalledWith([{ rc: [0, 2], to: [4.2, 2] }])
  })

  it('swaps two picked seats', () => {
    const { seat, getByRole, onDone } = setup()
    fireEvent.pointerDown(seat(1), { button: 0, pointerId: 1, ctrlKey: true })
    fireEvent.pointerDown(seat(4), { button: 0, pointerId: 1, ctrlKey: true })
    fireEvent.pointerDown(getByRole('button', { name: 'Swap seats A-1 and A-4' }), { button: 0, pointerId: 1 })
    expect(onDone).toHaveBeenCalledWith([{ rc: [0, 0], to: [4.2, 2] }, { rc: [0, 3], to: [0, 0] }])
  })
})
