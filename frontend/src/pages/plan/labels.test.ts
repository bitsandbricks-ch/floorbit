import { describe, expect, it } from 'vitest'
import { labelPlan, labelStyle, rowEnds } from './labels'

const CELL = 32

describe('labelPlan', () => {
  it('numbers every seat at the classic size up close', () => {
    const p = labelPlan(CELL, 1)          // 32 px a seat
    expect(p.seats).toBe('all')
    expect(p.num).toBe(11)
  })

  it('shrinks the numbers to fit the seat while they stay readable', () => {
    const p = labelPlan(CELL, 20 / CELL)  // 20 px a seat
    expect(p.seats).toBe('all')
    expect(p.num * (20 / CELL)).toBeGreaterThanOrEqual(9)
    expect(p.num).toBeLessThanOrEqual(CELL / 2)
  })

  it('keeps only the row ends when a number no longer fits', () => {
    expect(labelPlan(CELL, 15 / CELL).seats).toBe('ends')
    expect(labelPlan(CELL, 15 / CELL).rows).toBe(true)
  })

  it('writes nothing on specks, where the block summaries take over', () => {
    const p = labelPlan(CELL, 8 / CELL)
    expect(p.seats).toBe('none')
    expect(p.rows).toBe(false)
  })

  it('row letters stay readable when zoomed out but never outgrow a seat', () => {
    expect(labelPlan(CELL, 15 / CELL).row * (15 / CELL)).toBeGreaterThanOrEqual(12 * 0.99)
    expect(labelPlan(CELL, 13 / CELL).row).toBeLessThanOrEqual(CELL)
  })

  it('follows a screen that asks for numbers always or never', () => {
    expect(labelPlan(CELL, 8 / CELL, 'all').seats).toBe('all')
    expect(labelPlan(CELL, 8 / CELL, 'all').num).toBe(CELL / 2)
    expect(labelPlan(CELL, 2, 'none').seats).toBe('none')
  })

  it('hands the sizes to CSS', () => {
    expect(labelStyle(labelPlan(CELL, 1))['--seat-num']).toBe('11.00px')
  })
})

describe('rowEnds', () => {
  it('picks the first and last seat of each row', () => {
    const cells = [
      { seat: 'A-3', x: 64, y: 0 }, { seat: 'A-1', x: 0, y: 0 }, { seat: 'A-2', x: 32, y: 0 },
      { seat: 'A-4', x: 0, y: 32.2 }, { seat: 'A-5', x: 32, y: 31.9 },
      { seat: 'A-6', x: 0, y: 64 },
    ]
    expect([...rowEnds(cells)].sort()).toEqual(['A-1', 'A-3', 'A-4', 'A-5', 'A-6'])
  })
})
