import { describe, expect, it } from 'vitest'
import type { Widget } from '@/api/types'
import { calc, groupBy, groupKeys, merge, reduce, shapeData } from './combine'

const base = { id: 'w', size: 'small', refresh: 60, sub: '', link: '' } as const
const traffic: Widget = { ...base, label: 'Uplink A', type: 'series', unit: 'bit/s', series: [
  { label: 'Down', points: [[0, 10], [60, 30]] }, { label: 'Up', points: [[0, 1], [60, 3]] }] }
const power: Widget = { ...base, label: 'Uplink B', type: 'series', unit: 'bit/s', series: [{ label: 'Down', points: [[0, 5]] }] }
const watts: Widget = { ...base, label: 'Power', type: 'series', unit: 'W', series: [{ label: 'Hall', points: [[0, 900]] }] }
const states: Widget = { ...base, label: 'Switches', type: 'status', items: [
  { label: 'sw-a', state: 'up', detail: 'hall 1' }, { label: 'sw-b', state: 'down', detail: 'hall 1' },
  { label: 'sw-c', state: 'down', detail: 'hall 2' }] }
const table: Widget = { ...base, label: 'Ports', type: 'table',
  columns: [{ key: 'name', label: 'Switch' }, { key: 'hall', label: 'Hall' }, { key: 'used', label: 'Used' }],
  rows: [{ name: 'a', hall: '1', used: '10' }, { name: 'b', hall: '1', used: '20' }, { name: 'c', hall: '2', used: '6' }] }

describe('combining widget data', () => {
  it('calculates', () => {
    const v = [4, 1, 7]
    expect(['count', 'sum', 'avg', 'min', 'max', 'first', 'last'].map((c) => calc(v, c as never))).toEqual([3, 12, 4, 1, 7, 4, 7])
    expect(calc([], 'avg')).toBeNull()
    expect(calc([], 'count')).toBe(0)
  })
  it('merges lines of the same unit and names each by its source', () => {
    const { widget, dropped } = merge([traffic, power, watts])
    expect(widget.type === 'series' && widget.series.map((l) => l.label)).toEqual(['Uplink A · Down', 'Uplink A · Up', 'Uplink B'])
    expect(dropped).toEqual(['Power'])
  })
  it('turns numbers into a list, one per source', () => {
    const a: Widget = { ...base, label: 'Hall A', type: 'stat', value: 40, unit: '', tone: '', max: 50 }
    const b: Widget = { ...base, label: 'Hall B', type: 'stat', value: 30, unit: '', tone: '' }
    const { widget } = merge([a, b])
    expect(widget.type === 'list' && widget.items.map((i) => [i.label, i.number, i.max])).toEqual([['Hall A', 40, 50], ['Hall B', 30, undefined]])
  })
  it('adds up status lists and joins tables on their first column', () => {
    const { widget } = merge([states, { ...states, label: 'More', items: [{ label: 'sw-d', state: 'up', detail: '' }] }])
    expect(widget.type === 'status' && widget.items).toHaveLength(4)
    const other: Widget = { ...base, label: 'Errors', type: 'list', items: [{ label: 'a', value: '2', tone: '', number: 2 }, { label: 'z', value: '1', tone: '', number: 1 }] }
    const joined = merge([table, other]).widget
    expect(joined.type === 'table' && joined.columns.map((c) => c.label)).toEqual(['Switch', 'Ports · Hall', 'Ports · Used', 'Errors'])
    expect(joined.type === 'table' && joined.rows.find((r) => r.label === 'z')).toEqual({ label: 'z', '0.hall': '', '0.used': '', '1.value': '1' })
  })
  it('groups rows by a key, counting or calculating over the numbers', () => {
    expect(groupKeys(table).map((k) => k.key)).toEqual(['name', 'hall', 'used'])
    const byState = groupBy(states, 'state')
    expect(byState.type === 'list' && byState.items.map((i) => [i.label, i.number])).toEqual([['down', 2], ['up', 1]])
    const byHall = groupBy(table, 'hall', 'sum')
    expect(byHall.type === 'list' && byHall.items.map((i) => [i.label, i.number])).toEqual([['1', 30], ['2', 6]])
  })
  it('reduces to one number, or one per line', () => {
    expect(reduce(power, 'max')).toMatchObject({ type: 'stat', value: 5, unit: 'bit/s' })
    expect(reduce(states, 'count')).toMatchObject({ type: 'stat', value: 3, unit: '' })
    const perLine = reduce(traffic, 'avg')
    expect(perLine.type === 'list' && perLine.items.map((i) => [i.label, i.number])).toEqual([['Down', 20], ['Up', 2]])
  })
  it('runs the whole pipeline, ignoring a group key the data lacks', () => {
    const named: Widget = { ...table, type: 'table', rows: table.type === 'table' ? table.rows.map((r) => ({ ...r, hall: `H${r.hall}` })) : [] }
    expect(shapeData([named], { group_by: 'nope', reduce: 'sum' }).widget).toMatchObject({ type: 'stat', value: 36 })
  })
})
