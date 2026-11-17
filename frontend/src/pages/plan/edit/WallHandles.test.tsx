import { fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlanMark } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { WallHandles } from './WallHandles'

const ctx = { toPlan: (x: number, y: number) => ({ x, y }), scale: 1, shown: { x: 0, y: 0, w: 1600, h: 1000 } }
const size = { w: 1600, h: 1000 }
const wall: PlanMark = { id: 'w', kind: 'wall', x: 0, y: 100, x2: 320, y2: 100 }

function handles(props: Partial<React.ComponentProps<typeof WallHandles>> = {}) {
  const onDone = vi.fn(), onDraft = vi.fn()
  const r = renderWithApp(<svg><WallHandles ctx={ctx} mark={wall} size={size} cell={32} anchors={[]} onDraft={onDraft} onDone={onDone} {...props} /></svg>)
  return { ...r, onDone, onDraft }
}

describe('Wall handles', () => {
  it('shows each stretch\'s length in seats and its angle', () => {
    const { container } = handles()
    expect(container.querySelector('.fb-edit-measure')).toHaveTextContent('10 · 0°')
  })

  it('pulls a bend out of the middle of a stretch', () => {
    const { container, onDone } = handles()
    const dot = container.querySelector('.fb-edit-bend-add')!
    fireEvent.pointerDown(dot, { button: 0, pointerId: 1, clientX: 160, clientY: 100 })
    fireEvent.pointerMove(dot, { pointerId: 1, clientX: 160, clientY: 203 })
    fireEvent.pointerUp(dot, { pointerId: 1, clientX: 160, clientY: 203 })
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ points: [[160, 205]] }))   // on the 0.5 % grid
  })

  it('snaps an end onto another wall\'s corner', () => {
    const { container, onDone } = handles({ anchors: [{ x: 333, y: 141 }] })
    const end = container.querySelector('[data-handle="b"]')!
    fireEvent.pointerDown(end, { button: 0, pointerId: 1, clientX: 320, clientY: 100 })
    fireEvent.pointerMove(end, { pointerId: 1, clientX: 330, clientY: 138 })
    fireEvent.pointerUp(end, { pointerId: 1, clientX: 330, clientY: 138 })
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ x2: 333, y2: 141 }))
  })

  it('takes a bend out on double-click', () => {
    const { container, onDone } = handles({ mark: { ...wall, points: [[160, 200]] } })
    fireEvent.doubleClick(container.querySelector('[data-handle="bend-1"]')!)
    expect(onDone.mock.calls[0][0].points).toBeUndefined()
  })
})

