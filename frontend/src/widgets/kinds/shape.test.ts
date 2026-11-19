import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { bucketsOf, formatValue, kindsFor, partsOf, resolveKind, rowsOf, scaleOf, slices, stateCounts, statOf } from './shape'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const
const status: Widget = { ...base, type: 'status', items: [
  { label: 'sw-a', state: 'up', detail: '' }, { label: 'sw-b', state: 'down', detail: 'down 4 min' },
  { label: 'sw-c', state: 'warn', detail: '' }] }
const labels = { name: 'Name', value: 'Value', state: 'Detail' }

describe('widget shapes', () => {
  it('only offers kinds the data can be drawn as', () => {
    expect(kindsFor({ ...base, type: 'series', unit: '', series: [] })).toEqual(['graph', 'column', 'stat'])
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
})
