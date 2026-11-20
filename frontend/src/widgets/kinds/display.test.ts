import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { applyDisplay, displaysFor, mappingFor, toneAt } from './display'
import { formatValue } from './shape'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const
const steps = { thresholds: [{ at: 95, tone: 'err' as const }, { at: 80, tone: 'warn' as const }] }
const blocks: Widget = { ...base, type: 'list', items: [
  { label: 'B', value: '0', tone: '', number: 0 }, { label: 'A10', value: '9', tone: '', number: 9 },
  { label: 'A2', value: '90', tone: '', number: 90 }, { label: 'C', value: '50', tone: '', number: 50 }] }

describe('pane display', () => {
  it('takes the tone of the highest step reached, by value or share of the max', () => {
    expect(toneAt(85, steps)).toBe('warn')
    expect(toneAt(99, steps)).toBe('err')
    expect(toneAt(10, steps)).toBeNull()
    expect(toneAt(17, { ...steps, threshold_mode: 'percent' }, 20)).toBe('warn')
    expect(toneAt(19, { ...steps, threshold_mode: 'percent' })).toBeNull()
  })
  it('maps a value or range to a text', () => {
    const d = { mappings: [{ from: 0, to: 0, text: 'Down', tone: 'err' as const }, { from: 1, text: 'Up' }] }
    expect(mappingFor(0, d)?.text).toBe('Down')
    expect(mappingFor(7, d)?.text).toBe('Up')
    const stat = applyDisplay({ ...base, type: 'stat', value: 0, unit: 'x', tone: '' }, d)
    expect(stat).toMatchObject({ text: 'Down', tone: 'err', unit: '' })
  })
  it('sets the unit, decimals and short numbers', () => {
    expect(formatValue(1234.5, '', 'en', { short: true })).toEqual({ value: '1.2k', unit: '' })
    expect(formatValue(2, '', 'en', { decimals: 2 })).toEqual({ value: '2.00', unit: '' })
    expect(applyDisplay({ ...base, type: 'sparkline', points: [1], unit: '' }, { unit: 'ms' })).toMatchObject({ unit: 'ms' })
  })
  it('sorts, hides zero and keeps the top N', () => {
    const out = applyDisplay(blocks, { sort: 'value-desc', limit: 2, hide_zero: true, ...steps }, 'en')
    expect(out.type === 'list' && out.items.map((i) => [i.label, i.tone])).toEqual([['A2', 'warn'], ['C', '']])
    const names = applyDisplay(blocks, { sort: 'name-asc' })
    expect(names.type === 'list' && names.items.map((i) => i.label)).toEqual(['A2', 'A10', 'B', 'C'])
  })
  it('offers row settings only for rows and number settings only for numbers', () => {
    expect(displaysFor(blocks)).toEqual({ numbers: true, colours: true, rows: true })
    expect(displaysFor({ ...base, type: 'stat', value: 'ok', unit: '', tone: '' })).toEqual({ numbers: false, colours: false, rows: false })
  })
})
