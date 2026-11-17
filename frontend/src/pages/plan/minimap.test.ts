import { describe, expect, it } from 'vitest'
import { centreOn, showMinimap } from './minimap'

const fit = { x: 0, y: 0, w: 1600, h: 1000 }

describe('minimap', () => {
  it('shows only once part of the plan is off screen', () => {
    expect(showMinimap(fit, fit)).toBe(false)
    expect(showMinimap({ x: 0, y: 0, w: 1200, h: 750 }, fit)).toBe(false)
    expect(showMinimap({ x: 0, y: 0, w: 800, h: 500 }, fit)).toBe(true)
  })

  it('centres the view where the overview was clicked, keeping its size', () => {
    expect(centreOn({ x: 0, y: 0, w: 400, h: 250 }, { x: 800, y: 500 })).toEqual({ x: 600, y: 375, w: 400, h: 250 })
  })
})
