import { describe, expect, it } from 'vitest'
import type { PlanMark } from '@/api/types'
import { wallRoute } from './geometry'
import { handlesOf, measure, reshape, shapeBody, snapCorner, withRoute } from './reshape'

const size = { w: 1600, h: 1000 }

describe('reshape', () => {
  it('scales a label by how far the corner is dragged from its middle', () => {
    const m: PlanMark = { id: 'a', kind: 'text', x: 100, y: 100, text: 'Bar' }
    const out = reshape(m, 'scale', { x: 160, y: 140 }, { x: 130, y: 120 }, size, false)
    expect(out.scale).toBe(2)
    expect(shapeBody(out, size)).toEqual({ scale: 2 })
  })

  it('keeps the scale within limits', () => {
    const m: PlanMark = { id: 'a', kind: 'icon', x: 0, y: 0, icon: 'wc', scale: 4 }
    expect(reshape(m, 'scale', { x: 100, y: 0 }, { x: 10, y: 0 }, size, true).scale).toBe(8)
    expect(reshape(m, 'scale', { x: 0.1, y: 0 }, { x: 10, y: 0 }, size, true).scale).toBe(0.25)
  })

  it('moves a zone corner and keeps the opposite one', () => {
    const m: PlanMark = { id: 'z', kind: 'zone', x: 160, y: 100, w: 320, h: 200 }
    const out = reshape(m, 'nw', { x: 81, y: 52 }, { x: 160, y: 100 }, size, false)
    expect(out).toMatchObject({ x: 80, y: 50, w: 400, h: 250 })
    expect(shapeBody(out, size)).toEqual({ x: 5, y: 5, w: 25, h: 25 })
  })

  it('never turns a zone inside out', () => {
    const m: PlanMark = { id: 'z', kind: 'zone', x: 160, y: 100, w: 320, h: 200 }
    const out = reshape(m, 'se', { x: 0, y: 0 }, { x: 480, y: 300 }, size, true)
    expect(out.w).toBeGreaterThan(0)
    expect(out.h).toBeGreaterThan(0)
  })

  it("moves a wall's end, not onto the other end", () => {
    const m: PlanMark = { id: 'w', kind: 'wall', x: 0, y: 0, x2: 160, y2: 0 }
    expect(reshape(m, 'b', { x: 320, y: 98 }, { x: 160, y: 0 }, size, false)).toMatchObject({ x2: 320, y2: 100 })
    expect(reshape(m, 'b', { x: 1, y: 1 }, { x: 160, y: 0 }, size, false)).toBe(m)
  })

  it('puts a turned label’s handle on its turned corner', () => {
    const m: PlanMark = { id: 'a', kind: 'text', x: 0, y: 0, text: 'x', rotation: 90 }
    const [[, p]] = handlesOf(m, { x: 10, y: 5 })
    expect(p.x).toBeCloseTo(-5)
    expect(p.y).toBeCloseTo(10)
  })
})

describe('walls with bends', () => {
  const wall: PlanMark = { id: 'w', kind: 'wall', x: 0, y: 0, x2: 160, y2: 100, points: [[160, 0]] }

  it('keeps the bends between the ends, and sends them in %', () => {
    expect(wallRoute(wall)).toEqual([{ x: 0, y: 0 }, { x: 160, y: 0 }, { x: 160, y: 100 }])
    const bent = withRoute(wall, [{ x: 0, y: 0 }, { x: 80, y: 0 }, { x: 80, y: 100 }, { x: 160, y: 100 }])
    expect(bent.points).toEqual([[80, 0], [80, 100]])
    expect(shapeBody(bent, size)).toEqual({ x: 0, y: 0, x2: 10, y2: 10, points: [[5, 0], [5, 10]] })
    // Straight again: no bends left, and the server is told so.
    const straight = withRoute(wall, [{ x: 0, y: 0 }, { x: 160, y: 100 }])
    expect(straight.points).toBeUndefined()
    expect(shapeBody(straight, size).points).toEqual([])
  })

  it('snaps a corner onto another wall when near, else 15° steps with Shift, else the grid', () => {
    const anchors = [{ x: 100, y: 100 }]
    expect(snapCorner({ x: 104, y: 97 }, { anchors, reach: 8, size })).toEqual({ x: 100, y: 100 })
    expect(snapCorner({ x: 130, y: 97 }, { anchors, reach: 8, size })).toEqual({ x: 128, y: 95 })   // the 0.5 % grid
    const tilted = snapCorner({ x: 100, y: 3 }, { from: { x: 0, y: 0 }, angle: true, size })
    expect(tilted.y).toBeCloseTo(0)
    expect(snapCorner({ x: 13, y: 7 }, { free: true, size })).toEqual({ x: 13, y: 7 })
  })

  it('reads a stretch in seats and degrees, counter-clockwise from east', () => {
    expect(measure({ x: 0, y: 0 }, { x: 64, y: 0 }, 32)).toBe('2 · 0°')
    expect(measure({ x: 0, y: 0 }, { x: 0, y: -48 }, 32)).toBe('1.5 · 90°')
    expect(measure({ x: 0, y: 0 }, { x: -32, y: 0 }, 32)).toBe('1 · 180°')
  })
})
