import { describe, expect, it } from 'vitest'
import { labelPlan, labelStyle } from './labels'

const CELL = 32

describe('labelPlan', () => {
  it('numbers every seat at the classic size up close', () => {
    const p = labelPlan(CELL, 1)          // 32 px a seat
    expect(p.seats).toBe('all')
    expect(p.num).toBe(11)
    expect(p.rows).toBe(true)
  })

  it('drops seat numbers below 30 px a seat but keeps the row labels (#1471)', () => {
    const p = labelPlan(CELL, 20 / CELL)  // 20 px a seat
    expect(p.seats).toBe('none')
    expect(p.rows).toBe(true)
  })

  it('keeps the row letters on small seats, where they replace the block tags (2026-11-26)', () => {
    const p = labelPlan(CELL, 8 / CELL)
    expect(p.seats).toBe('none')
    expect(p.rows).toBe(true)
  })

  it('writes nothing on specks', () => {
    expect(labelPlan(CELL, 4 / CELL).rows).toBe(false)
  })

  it('keeps row letters small: at most 11 px, at least 7 px while the seat has room', () => {
    for (const seatPx of [6, 8, 12, 18, 40, 80]) {
      const s = seatPx / CELL
      const px = labelPlan(CELL, s).row * s
      expect(px).toBeLessThanOrEqual(11.001)
      expect(px).toBeLessThanOrEqual(Math.max(seatPx * 0.55, 7) + 0.001)
      expect(px).toBeGreaterThanOrEqual(Math.min(7, seatPx * 0.95) - 0.001)
    }
  })

  it('prints row labels at half a seat on paper', () => {
    expect(labelPlan(CELL, 2, 'auto', true).row).toBeCloseTo(CELL * 0.55)
    expect(labelPlan(CELL, 2, 'auto', true).rows).toBe(true)
  })

  it('follows a screen that asks for numbers always or never', () => {
    expect(labelPlan(CELL, 8 / CELL, 'all').seats).toBe('all')
    expect(labelPlan(CELL, 8 / CELL, 'all').num).toBe(CELL / 2)
    expect(labelPlan(CELL, 2, 'none').seats).toBe('none')
    expect(labelPlan(CELL, 2, 'none').rows).toBe(false)
  })

  it('hands the sizes to CSS', () => {
    expect(labelStyle(labelPlan(CELL, 1))['--seat-num']).toBe('11.00px')
    expect(labelStyle(labelPlan(CELL, 1))['--row-lbl']).toBe('11.00px')
  })
})
