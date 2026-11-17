import { describe, expect, it } from 'vitest'
import { fitFactor, framePct, scaleFrame, seatMetres } from './background'

describe('placing and calibrating the background', () => {
  it('keeps the frame in % of the plan', () => {
    expect(framePct({ x: -80, y: 100, w: 1920, h: 800 }, { w: 1600, h: 1000 })).toEqual({ x: -5, y: 10, w: 120, h: 80 })
  })
  it('scales round the line\'s start, which stays put', () => {
    expect(scaleFrame({ x: 0, y: 0, w: 1600, h: 1000 }, { x: 400, y: 500 }, 0.5)).toEqual({ x: 200, y: 250, w: 800, h: 500 })
  })
  it('turns a measured line into metres per seat, or a factor to fit the drawing to the seats', () => {
    expect(seatMetres(20, 16)).toBe(0.8)
    // 10 m on a drawing where the line is 25 seats, at 0.8 m a seat: it should be 12.5 seats.
    expect(fitFactor(25, 10, 0.8)).toBe(0.5)
  })
})
