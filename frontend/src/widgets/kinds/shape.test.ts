import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { formatValue, kindsFor, resolveKind, rowsOf, stateCounts, statOf } from './shape'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const
const status: Widget = { ...base, type: 'status', items: [
  { label: 'sw-a', state: 'up', detail: '' }, { label: 'sw-b', state: 'down', detail: 'down 4 min' },
  { label: 'sw-c', state: 'warn', detail: '' }] }
const labels = { name: 'Name', value: 'Value', state: 'Detail' }

describe('widget shapes', () => {
  it('only offers kinds the data can be drawn as', () => {
    expect(kindsFor('series')).toEqual(['graph', 'stat'])
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
})
