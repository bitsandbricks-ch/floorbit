import { describe, expect, it } from 'vitest'
import { framed, zoomAt } from './camera'

describe('topology camera', () => {
  const base = { x: 0, y: 0, w: 400, h: 200 }

  it('frames a small picture no bigger than the largest scale, centred', () => {
    const v = framed(base, 1200, 800, 1, 1.6)
    expect(v.w).toBeCloseTo(750) // 1200 / 1.6
    expect(v.h).toBeCloseTo(500)
    expect(v.x + v.w / 2).toBeCloseTo(200)
    expect(v.y + v.h / 2).toBeCloseTo(100)
  })

  it('keeps a big picture readable and starts at its top', () => {
    const big = { x: 0, y: 0, w: 4000, h: 2000 }
    const v = framed(big, 1000, 600, 1, 1.6)
    expect(v.w).toBe(1000)
    expect(v.h).toBe(600)
    expect(v.y).toBe(0)
    expect(v.x).toBe(1500)
  })

  it('has the pane\'s shape, so the grid fills it', () => {
    const v = framed(base, 900, 300, 0.5, 4)
    expect(v.w / v.h).toBeCloseTo(3)
  })

  it('zooms around a point and keeps the shape', () => {
    const v = zoomAt({ x: 0, y: 0, w: 300, h: 100 }, base, 2, { x: 150, y: 50 })
    expect(v).toEqual({ x: 75, y: 25, w: 150, h: 50 })
  })
})
