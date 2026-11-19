import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { binsOf, bucketsOf, formatValue, kindsFor, looksFor, partsOf, resolveKind, rowsOf, scaleOf, slices, stackLines, stateCounts, statOf, trendOf, valuesOf } from './shape'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const
const status: Widget = { ...base, type: 'status', items: [
  { label: 'sw-a', state: 'up', detail: '' }, { label: 'sw-b', state: 'down', detail: 'down 4 min' },
  { label: 'sw-c', state: 'warn', detail: '' }] }
const labels = { name: 'Name', value: 'Value', state: 'Detail' }

describe('widget shapes', () => {
  it('only offers kinds the data can be drawn as', () => {
    expect(kindsFor({ ...base, type: 'series', unit: '', series: [] })).toEqual(['graph', 'column', 'histogram', 'stat'])
    expect(resolveKind(status, 'graph')).toBe('status')
    expect(resolveKind(status, 'stat')).toBe('stat')
  })
  it('counts a status as how many are up, toned by the worst', () => {
    expect(statOf(status, 'en')).toMatchObject({ value: '1', of: 3, tone: 'err' })
    expect(stateCounts(status)).toEqual([['down', 1], ['warn', 1], ['up', 1]])
  })
  it('puts the worst rows first, so the problem is what fits', () => {
    expect(rowsOf(status, labels).rows.map((r) => r.cells.label)).toEqual(['sw-b', 'sw-c', 'sw-a'])
  })
  it('scales bits and bytes', () => {
    expect(formatValue(5_200_000_000, 'bit/s', 'en')).toEqual({ value: '5.2', unit: 'Gbit/s' })
    expect(formatValue(1234, '', 'en')).toEqual({ value: '1,234', unit: '' })
  })
  it('reads the latest value of a series', () => {
    const w: Widget = { ...base, type: 'series', unit: 'bit/s', series: [{ label: 'Down', points: [[1, 10], [2, 2000]] }] }
    expect(statOf(w, 'en')).toMatchObject({ value: '2', unit: 'kbit/s' })
  })
  it('offers a gauge only with a scale, bars and a pie only with numbers', () => {
    expect(kindsFor({ ...base, type: 'stat', value: 3, unit: '', tone: '' })).toEqual(['stat'])
    expect(kindsFor({ ...base, type: 'stat', value: 3, unit: '', tone: '', max: 10 })).toEqual(['stat', 'gauge'])
    const plain: Widget = { ...base, type: 'list', items: [{ label: 'a', value: 'x', tone: '' }] }
    expect(kindsFor(plain)).not.toContain('bar')
    expect(resolveKind(plain, 'pie')).toBe('list')
  })
  it('reads parts from states and from numbers, a max making a bar gauge', () => {
    const name = (s: string) => s
    expect(partsOf(status, name).map((p) => [p.label, p.value])).toEqual([['down', 1], ['warn', 1], ['up', 1]])
    const blocks: Widget = { ...base, type: 'list', items: [{ label: 'A', value: '2 / 3', tone: '', number: 2, max: 3 }] }
    expect(partsOf(blocks, name)[0]).toMatchObject({ label: 'A', value: 2, max: 3, text: '2 / 3' })
    expect(scaleOf({ ...base, type: 'stat', value: 5, unit: '', tone: '', max: 20 })).toEqual({ value: 5, min: 0, max: 20 })
  })
  it('keeps a pie to seven slices, the rest as other', () => {
    const parts = Array.from({ length: 10 }, (_, i) => ({ label: `p${i}`, value: i + 1, text: '', colour: '' }))
    const out = slices(parts, 'Other', 'en')
    expect(out).toHaveLength(7)
    expect(out[6]).toMatchObject({ label: 'Other', value: 1 + 2 + 3 + 4 })
  })
  it('cuts time data into columns, each the average of its slice', () => {
    const b = bucketsOf([{ label: 'a', points: [[0, 2], [10, 4], [20, 6], [30, 8]] }, { label: 'b', points: [[0, 1]] }], 2)
    expect(b).toHaveLength(2)
    expect(b[0].values).toEqual([3, 1])
    expect(b[1].values).toEqual([7, null])
  })
  it('stacks lines bottom to top, or to 100 %', () => {
    const lines = [{ label: 'a', points: [[0, 1], [10, 3]] as [number, number][] }, { label: 'b', points: [[0, 3], [10, 1]] as [number, number][] }]
    expect(stackLines(lines, 'stacked')[1]).toEqual([[0, 1, 4], [10, 3, 4]])
    expect(stackLines(lines, 'percent')[0]).toEqual([[0, 0, 25], [10, 0, 75]])
  })
  it('counts values in round ranges for a histogram', () => {
    const bins = binsOf([1, 2, 3, 4, 11, 12, 19])
    expect(bins.map((b) => [b.from, b.to])).toEqual([[0, 10], [10, 20]])
    expect(bins.map((b) => b.count)).toEqual([4, 3])
    expect(binsOf([7, 7])).toEqual([{ from: 7, to: 7, count: 2 }])
    expect(valuesOf({ ...base, type: 'series', unit: '', series: [{ label: 'a', points: [[0, 5], [1, 6]] }] })).toEqual([5, 6])
  })
  it('fits a straight trend and a rolling average', () => {
    expect(trendOf([[0, 0], [1, 2], [2, 4]], 'linear')).toEqual([[0, 0], [2, 4]])
    expect(trendOf([[0, 0], [1, 3], [2, 0]], 'average')[1]).toEqual([1, 1])
    expect(trendOf([[0, 1]], 'linear')).toEqual([])
  })
  it('reads table rows as bars with a segment per number column', () => {
    const t: Widget = { ...base, type: 'table', columns: [{ key: 'n', label: 'Name' }, { key: 'a', label: 'A' }, { key: 'b', label: 'B' }],
      rows: [{ n: 'x', a: '2', b: '3' }] }
    const [part] = partsOf(t, (s) => s)
    expect(part).toMatchObject({ label: 'x', value: 5 })
    expect(part.segments?.map((g) => [g.label, g.value])).toEqual([['A', 2], ['B', 3]])
  })
  it('offers stacking only with two series, trends only over time', () => {
    const two: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'a', points: [] }, { label: 'b', points: [] }] }
    expect(looksFor(two, 'graph')).toEqual(['stack', 'style', 'trend', 'legend'])
    expect(looksFor(two, 'histogram')).toEqual([])
    expect(looksFor({ ...base, type: 'sparkline', unit: '', points: [1] }, 'column')).toEqual(['trend'])
  })
})
