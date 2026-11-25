import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PlanDrawing, PlanMark, SeatViewData } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { PlanMarks } from '../PlanMarks'
import { snapToGuides } from './arrange'
import { TOOL_GESTURE, TOOL_KEYS } from './tools'
import { WalkwayFields } from './WalkwayFields'

const walkway: PlanMark = { id: 'k1', kind: 'walkway', x: 0, y: 200, x2: 800, y2: 200, width: 3 }

describe('walkways (#1564)', () => {
  it('draws a band as wide as the walkway, in seats', () => {
    const drawing = { shapes: [], icons: {}, cell: 32, marks: [walkway] } as unknown as PlanDrawing
    const { container } = render(<svg><PlanMarks drawing={drawing} /></svg>)
    expect(container.querySelector('.walkway-band')!.getAttribute('stroke-width')).toBe('96')
    expect(container.querySelector('.walkway-mid')).not.toBeNull()
  })

  it('shows on the Safety layer as well as its own', () => {
    const drawing = { shapes: [], icons: {}, cell: 32, marks: [walkway, { id: 'w', kind: 'wall', x: 0, y: 0, x2: 9, y2: 0 }] } as unknown as PlanDrawing
    const only = (on: string[]) => render(<svg><PlanMarks drawing={drawing} layers={{ on: new Set(on) as never, fade: {} }} /></svg>).container
    expect(only(['safety']).querySelector('.walkway')).not.toBeNull()
    expect(only(['safety']).querySelector('.wall')).toBeNull()
    expect(only(['marks']).querySelector('.walkway')).not.toBeNull()
    expect(only(['network']).querySelector('.walkway')).toBeNull()
  })

  it('lets a seat block snap with its seats on the walkway edge', () => {
    // The band runs from y 152 to 248; a block 32 high (one row) below it, a little off.
    const data = {
      size: { w: 1600, h: 1000 }, switches: [],
      drawing: { box: '0 0 1600 1000', cell: 32, marks: [walkway], shapes: [{ id: 'b', cx: 400, cy: 270, rotation: 0, w: 128, h: 32, cells: [] }] },
    } as unknown as SeatViewData
    const { d } = snapToGuides(data, [{ kind: 'block', id: 'b' }], { x: 0, y: 0 }, 10, [{ kind: 'mark', id: 'k1' }])
    expect(270 + d.y - 16).toBe(248)
  })

  it('is a line tool on K', () => {
    expect(TOOL_GESTURE.walkway).toBe('line')
    expect(TOOL_KEYS.walkway).toBe('k')
  })

  it('changes its width and straightens its bends', () => {
    const onWidth = vi.fn(), onStraighten = vi.fn()
    renderWithApp(<WalkwayFields mark={{ ...walkway, points: [[400, 300]] }} onWidth={onWidth} onStraighten={onStraighten} />)
    const width = screen.getByRole('textbox', { name: 'Width' })
    fireEvent.change(width, { target: { value: '4' } })
    fireEvent.blur(width)
    expect(onWidth).toHaveBeenCalledWith(3, 4)
    fireEvent.click(screen.getByRole('button', { name: /Straighten/ }))
    expect(onStraighten).toHaveBeenCalled()
  })
})
