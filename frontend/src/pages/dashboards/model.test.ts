import { describe, expect, it } from 'vitest'
import type { PlanDrawing } from '@/api/types'
import { type Node, areaView, at, depth, paneRange, panes, planRows, rangedUrl, remove, resize, seatsIn, split, starter } from './model'

const empty: Node = { pane: { kind: 'empty' } }

describe('splitting', () => {
  it('starts with Mike\'s example: hall left, two panes right', () => {
    const root = starter()
    expect(panes(root)).toBe(3)
    expect(depth(root)).toBe(2)
  })

  it('adds a part next to a pane in the same direction', () => {
    const root = split({ split: 'row', sizes: [50, 50], children: [empty, empty] }, [1], 'row')
    expect('split' in root && root.children.length).toBe(3)
    expect('split' in root && root.sizes).toEqual([50, 25, 25])
  })

  it('nests a split for the other direction', () => {
    const root = split(starter(), [0], 'column')
    const left = at(root, [0])!
    expect('split' in left && left.split).toBe('column')
    expect(panes(root)).toBe(4)
  })

  it('takes a part out and folds a split left with one part', () => {
    const root = remove(starter(), [1, 0])
    const right = at(root, [1])!
    expect('pane' in right).toBe(true)
    expect(panes(root)).toBe(2)
    expect(remove(empty, [])).toEqual(empty)
  })

  it('moves a border, keeping each part at least 5 percent', () => {
    const root = resize({ split: 'row', sizes: [50, 50], children: [empty, empty] }, [], 0, 70)
    expect('split' in root && root.sizes).toEqual([70, 30])
    const squeezed = resize(root, [], 0, 99)
    expect('split' in squeezed && squeezed.sizes).toEqual([95, 5])
  })
})

const drawing: PlanDrawing = {
  box: '0 0 1600 1000', cell: 32,
  shapes: [{ cx: 400, cy: 300, rotation: 0, w: 64, h: 32, name: 'A', cells: [{ seat: 'A-1', x: -32, y: -16 }, { seat: 'A-2', x: 0, y: -16 }] as never }],
  marks: [{ id: 'z1', kind: 'zone', x: 1000, y: 600, w: 200, h: 100, label: 'VIP' }],
}

describe('areas', () => {
  it('finds a zone, a block and the whole hall', () => {
    expect(areaView({ kind: 'zone', id: 'z1' }, drawing)).toEqual({ x: 976, y: 576, w: 248, h: 148 })
    const block = areaView({ kind: 'block', id: 'A' }, drawing)!
    expect(block.x).toBeLessThan(368)
    expect(block.x + block.w).toBeGreaterThan(432)
    const hall = areaView({ kind: 'hall' }, drawing)!
    expect(hall.x + hall.w).toBeGreaterThanOrEqual(1200)
    expect(areaView({ kind: 'zone', id: 'gone' }, drawing)).toBeNull()
  })

  it('counts the seats inside an area', () => {
    expect(seatsIn(drawing, { x: 350, y: 250, w: 100, h: 100 })).toEqual(['A-1', 'A-2'])
    expect(seatsIn(drawing, { x: 900, y: 500, w: 400, h: 300 })).toEqual([])
  })
})

describe('a pane\'s time range (#960)', () => {
  it('asks only a tile that takes it', () => {
    const tile = { url: '/api/dashboard/floorbit/traffic', ranges: true }
    expect(rangedUrl(tile, { range: '6h', compare: 'day' })).toBe('/api/dashboard/floorbit/traffic?range=6h&compare=day')
    expect(rangedUrl(tile, {})).toBe(tile.url)
    expect(rangedUrl({ url: '/x' }, { range: '1h' })).toBe('/x')
  })

  it('follows the dashboard\'s time unless the pane picks its own', () => {
    expect(paneRange({}, '6h').range).toBe('6h')
    expect(paneRange({ range: '1h' }, '6h').range).toBe('1h')
    expect(paneRange({ compare: 'day' }, 'event')).toEqual({ range: 'event', compare: undefined })
    expect(paneRange({ compare: 'day' }, '24h').compare).toBe('day')
  })

  it('asks for marks only from a tile that has them', () => {
    expect(rangedUrl({ url: '/t', ranges: true, marks: true }, { range: '1h', events: true })).toBe('/t?range=1h&marks=1')
    expect(rangedUrl({ url: '/t' }, { events: true })).toBe('/t')
  })
})

describe('rows (#1078)', () => {
  const two: PlanDrawing = {
    box: '0 0 1600 1000', cell: 32, marks: [],
    shapes: [
      { id: 'b1', cx: 400, cy: 300, rotation: 0, w: 64, h: 64, name: '', row_list: [{ id: 'r-c', name: 'C' }, { id: 'r-d', name: 'D' }],
        cells: [{ seat: 'C-1', x: -32, y: -32, rc: [0, 0] }, { seat: 'C-2', x: 0, y: -32, rc: [0, 1] },
          { seat: 'D-1', x: -32, y: 0, rc: [1, 0] }, { seat: 'D-2', x: 0, y: 0, rc: [1, 1] }] as never },
      { id: 'b2', cx: 800, cy: 300, rotation: 0, w: 32, h: 64, name: 'A', row_list: [{ id: 'r-a1', name: 'A 1' }, { id: 'r-a2', name: 'A 2' }],
        cells: [{ seat: 'A-1', x: -16, y: -32, rc: [0, 0] }, { seat: 'A-2', x: -16, y: 0, rc: [1, 0] }] as never },
    ],
  }

  it('lists each row of each block with its seats, by the server id and name', () => {
    const rows = planRows(two)
    expect(rows.map((r) => [r.id, r.name, r.cells.map((c) => c.seat)])).toEqual([
      ['r-c', 'C', ['C-1', 'C-2']], ['r-d', 'D', ['D-1', 'D-2']], ['r-a1', 'A 1', ['A-1']], ['r-a2', 'A 2', ['A-2']]])
  })

  it('zooms to one row, centred on its seats', () => {
    const view = areaView({ kind: 'row', id: 'r-c' }, two)!
    expect(seatsIn(two, view)).toEqual(expect.arrayContaining(['C-1', 'C-2']))
    expect(view.y + view.h / 2).toBe(300 - 32 + 16)   // the middle of row C, not of the block
    expect(areaView({ kind: 'row', id: 'gone' }, two)).toBeNull()
  })
})
