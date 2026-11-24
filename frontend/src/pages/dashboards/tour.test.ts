import { describe, expect, it } from 'vitest'
import type { PlanDrawing } from '@/api/types'
import { freshProblems, problemView, tourStops } from './tour'

// Two blocks side by side and one below them; block "b" has three rows of four seats.
const cells = (p: string) => [0, 1, 2].flatMap((r) => [0, 1, 2, 3].map((c) => ({ seat: `${p}-${r}${c}`, x: c * 20 - 40, y: r * 20 - 30, rc: [r, c] })))
const drawing = {
  box: '0 0 1000 1000', cell: 20, marks: [],
  shapes: [
    { id: 'c', cx: 300, cy: 600, rotation: 0, w: 80, h: 60, name: 'Lower', cells: cells('C') },
    { id: 'b', cx: 500, cy: 200, rotation: 0, w: 80, h: 60, name: '', cells: cells('B'),
      row_list: [{ id: 'b:0', name: 'B0' }, { id: 'b:1', name: 'B1' }, { id: 'b:2', name: 'B2' }] },
    { id: 'a', cx: 200, cy: 210, rotation: 0, w: 80, h: 60, name: 'Left', cells: cells('A') },
    { id: 'x', cx: 0, cy: 0, rotation: 0, w: 10, h: 10, name: 'Empty', cells: [] },
  ],
} as unknown as PlanDrawing
const home = { x: 0, y: 0, w: 1000, h: 1000 }
const names = { whole: 'Main hall', block: (b: PlanDrawing['shapes'][number]) => b.name || b.id || '' }
const views = [
  { id: 'v1', name: 'VIP', hall: 'h', view: { x: 1, y: 2, w: 3, h: 4 }, show: 'problems' as const },
  { id: 'v2', name: 'Other hall', hall: 'other', view: { x: 1, y: 2, w: 3, h: 4 }, show: 'all' as const },
]

describe('tourStops', () => {
  it('goes whole hall, blocks top to bottom and left to right, then this hall\'s views', () => {
    const stops = tourStops(drawing, home, { whole: true, blocks: true, views: ['v2', 'v1'] }, views, 'h', names)
    expect(stops.map((s) => s.label)).toEqual(['Main hall', 'Left', 'b', 'Lower', 'VIP'])
    expect(stops[4]).toMatchObject({ key: 'view:v1', view: { x: 1, y: 2, w: 3, h: 4 }, show: 'problems' })
  })
  it('leaves out what the pane turned off', () => {
    expect(tourStops(drawing, home, { whole: false, blocks: false, views: ['v1'] }, views, 'h', names).map((s) => s.key)).toEqual(['view:v1'])
  })
})

describe('problemView', () => {
  it('shows the seat\'s row and the rows either side', () => {
    const v = problemView(drawing, 'B-11')!
    // Row middles at y 180, 200, 220 (block middle 200, rows -30..10 plus half a seat), two seats margin.
    expect(v.y).toBeCloseTo(140)
    expect(v.h).toBeCloseTo(120)
  })
  it('keeps at least a few seats of hall around a lone seat', () => {
    const v = problemView(drawing, 'A-00')!
    expect(v.w).toBeGreaterThanOrEqual(240)
    expect(v.h).toBeGreaterThanOrEqual(120)
  })
  it('is null for a seat not on the plan', () => {
    expect(problemView(drawing, 'Z-1')).toBeNull()
  })
})

describe('freshProblems', () => {
  it('names only seats that just got a problem, none on the first look', () => {
    expect(freshProblems(null, new Set(['a']))).toEqual([])
    expect(freshProblems(new Set(['a']), new Set(['a', 'b']))).toEqual(['b'])
  })
})
