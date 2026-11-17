import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PlanDrawing } from '@/api/types'
import { PlanMarks } from './PlanMarks'

describe('marks in their own colour', () => {
  it('draws a picked colour and leaves the theme colour to the stylesheet otherwise', () => {
    const drawing = {
      shapes: [], icons: {},
      marks: [
        { id: 'a', kind: 'wall', x: 0, y: 0, x2: 10, y2: 0, tint: '#e03131' },
        { id: 'b', kind: 'wall', x: 0, y: 5, x2: 10, y2: 5 },
        { id: 'z', kind: 'zone', x: 0, y: 0, w: 5, h: 5, tint: '#1c7ed6' },
        { id: 't', kind: 'text', x: 0, y: 0, text: 'Bar', tint: '#2f9e44' },
      ],
    } as unknown as PlanDrawing
    const { container } = render(<svg><PlanMarks drawing={drawing} /></svg>)
    const walls = container.querySelectorAll('.wall')
    expect(walls[0].getAttribute('style')).toContain('rgb(224, 49, 49)')
    expect(walls[1].getAttribute('style')).toBeNull()
    expect(container.querySelector('.zone')!.getAttribute('style')).toContain('--zone: #1c7ed6')
    expect(container.querySelector('.label')!.getAttribute('style')).toContain('rgb(47, 158, 68)')
  })
})
