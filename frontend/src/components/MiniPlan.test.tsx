import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PlanShape } from '@/api/types'
import { MiniPlan } from './MiniPlan'

const shape: PlanShape = { cx: 100, cy: 100, rotation: 0, w: 40, h: 20, name: 'A', cells: [{ seat: 'A-1', x: -20, y: -10, hit: false, on: null }] }

describe('MiniPlan', () => {
  it('draws block names over what the page adds, so an access point never hides them (#1418)', () => {
    const { container } = render(
      <MiniPlan drawing={{ box: '0 0 200 200', cell: 20, shapes: [shape] }} label="Hall">
        <circle className="ap" cx={100} cy={70} r={24} />
      </MiniPlan>,
    )
    const svg = container.querySelector('svg')!
    const order = [...svg.children].map((e) => e.getAttribute('class'))
    expect(order.indexOf('name')).toBeGreaterThan(order.indexOf('ap'))
    expect(svg.querySelector('text.name')?.textContent).toBe('A')
  })
})
