import { fireEvent, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import type { Widget } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { FitWidget } from './FitWidget'

const base = { id: 'w', label: 'W', size: 'small', refresh: 60, sub: '', link: '' } as const
const items = Array.from({ length: 30 }, (_, i) => ({ label: `sw-${String(i).padStart(2, '0')}`, state: i < 2 ? 'down' : 'up', detail: '' }) as const)
const status: Widget = { ...base, type: 'status', items: [...items] }

// jsdom lays nothing out: give every box the size the test wants.
let size = { w: 0, h: 0 }
beforeAll(() => {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => size.w)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(() => size.h)
})
afterAll(() => vi.restoreAllMocks())

describe('FitWidget', () => {
  it('shows a number in a small box', () => {
    size = { w: 150, h: 90 }
    renderWithApp(<FitWidget widget={status} />)
    expect(document.querySelector('[data-level]')).toHaveAttribute('data-level', 's')
    expect(screen.getByText('28')).toBeInTheDocument()
  })

  it('shows the rows that fit and how many more, worst first', () => {
    size = { w: 300, h: 140 }
    const more = vi.fn()
    renderWithApp(<FitWidget widget={status} onMore={more} />)
    expect(document.querySelectorAll('tbody tr')).toHaveLength(4)
    expect(screen.getAllByRole('img', { name: 'Down' })).toHaveLength(2)
    fireEvent.click(screen.getByText('+26 more'))
    expect(more).toHaveBeenCalled()
  })

  it('pages, sorts and filters inside a large box', () => {
    size = { w: 700, h: 300 }
    const table: Widget = { ...base, type: 'table', columns: [{ key: 'n', label: 'N' }],
      rows: Array.from({ length: 40 }, (_, i) => ({ n: `row ${i + 1}` })) }
    renderWithApp(<FitWidget widget={table} />)
    expect(screen.getByText('row 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.queryByText('row 1')).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter' }), { target: { value: 'row 40' } })
    expect(screen.getByText('row 40')).toBeInTheDocument()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1)
  })

  it('draws a series as a graph with a legend', () => {
    size = { w: 600, h: 300 }
    const series: Widget = { ...base, type: 'series', unit: 'bit/s', series: [
      { label: 'Download', points: [[1800000000, 1e9], [1800000060, 2e9]] }, { label: 'Upload', points: [[1800000000, 1e8], [1800000060, 2e8]] }] }
    renderWithApp(<FitWidget widget={series} />)
    expect(screen.getByRole('img', { name: 'Graph: W' })).toBeInTheDocument()
    expect(screen.getByText('2 Gbit/s')).toBeInTheDocument()
  })

  it('draws a stat with a scale as a gauge', () => {
    size = { w: 300, h: 220 }
    renderWithApp(<FitWidget widget={{ ...base, type: 'stat', value: 86, unit: 'of 112', tone: '', min: 0, max: 112 }} pick="gauge" />)
    expect(screen.getByRole('img', { name: '86 of 112 (77 %)' })).toBeInTheDocument()
  })

  it('draws numbers as bars, a block filling its own track', () => {
    size = { w: 400, h: 200 }
    const blocks: Widget = { ...base, type: 'list', items: [
      { label: 'A', value: '10 / 40', tone: '', number: 10, max: 40 }, { label: 'B', value: '30 / 30', tone: '', number: 30, max: 30 }] }
    renderWithApp(<FitWidget widget={blocks} pick="bar" />)
    expect(screen.getByTitle('A: 10 / 40 (25 %)')).toBeInTheDocument()
    expect(screen.getByTitle('B: 30 / 30 (100 %)')).toBeInTheDocument()
  })

  it('draws states as a pie with a legend', () => {
    size = { w: 500, h: 220 }
    renderWithApp(<FitWidget widget={status} pick="pie" />)
    expect(screen.getByRole('img', { name: 'Pie: Up 28, Down 2' })).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('draws numbers as vertical bars and time data as columns', () => {
    size = { w: 400, h: 220 }
    const blocks: Widget = { ...base, type: 'list', items: [{ label: 'A', value: '10 / 40', tone: '', number: 10, max: 40 }] }
    const { unmount } = renderWithApp(<FitWidget widget={blocks} pick="column" />)
    expect(screen.getByTitle('A: 10 / 40 (25 %)')).toBeInTheDocument()
    unmount()
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 1], [1800000060, 2]] }] }
    renderWithApp(<FitWidget widget={series} pick="column" />)
    expect(screen.getByRole('img', { name: 'Columns: W' })).toBeInTheDocument()
  })

  it('stacks lines to 100 % with a dashed trend', () => {
    size = { w: 600, h: 300 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [
      { label: 'Download', points: [[1800000000, 3], [1800000060, 1]] }, { label: 'Upload', points: [[1800000000, 1], [1800000060, 3]] }] }
    const { container } = renderWithApp(<FitWidget widget={series} look={{ stack: 'percent', style: 'area', trend: 'linear' }} />)
    expect(screen.getByText('100 %')).toBeInTheDocument()
    expect(container.querySelectorAll('.fb-w-trend')).toHaveLength(2)
  })

  it('counts values in ranges as a histogram', () => {
    size = { w: 400, h: 220 }
    const blocks: Widget = { ...base, type: 'list', items: [1, 2, 3, 11].map((n) => ({ label: `b${n}`, value: String(n), tone: '' as const, number: n })) }
    renderWithApp(<FitWidget widget={blocks} pick="histogram" />)
    expect(screen.getByRole('img', { name: /^Histogram: W/ })).toBeInTheDocument()
    expect(screen.getByTitle('0–5: 3')).toBeInTheDocument()
  })

  it('stacks the number columns of a table row in one bar', () => {
    size = { w: 400, h: 200 }
    const table: Widget = { ...base, type: 'table', columns: [{ key: 'n', label: 'Name' }, { key: 'a', label: 'In' }, { key: 'b', label: 'Out' }],
      rows: [{ n: 'core', a: '2', b: '3' }] }
    const { container } = renderWithApp(<FitWidget widget={table} pick="bar" look={{ stack: 'stacked' }} />)
    expect(container.querySelector('.fb-w-hstack')).not.toBeNull()
    expect(screen.getByText('In')).toBeInTheDocument()
  })

  it('shows the legend calculations a pane picks', () => {
    size = { w: 600, h: 300 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 2], [1800000060, 6]] }] }
    renderWithApp(<FitWidget widget={series} look={{ legend: ['min', 'avg'] }} />)
    expect(screen.getByText('Min')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('draws colour steps as lines on a graph and shows a mapped value as text', () => {
    size = { w: 600, h: 300 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 2], [1800000060, 10]] }] }
    const { container, unmount } = renderWithApp(<FitWidget widget={series} look={{ thresholds: [{ at: 5, tone: 'warn' }] }} />)
    expect(container.querySelector('.fb-w-step.fb-tone-warn')).not.toBeNull()
    unmount()
    size = { w: 200, h: 100 }
    renderWithApp(<FitWidget widget={{ ...base, type: 'stat', value: 0, unit: '', tone: 'err', text: 'Down' }} />)
    expect(screen.getByText('Down')).toBeInTheDocument()
  })

  it('picks its level from the whole widget, so a sub line can not make it flap (#1010)', () => {
    // The drawing area is 20px shorter than the widget when the sub line shows: a level taken from
    // the area would drop to small, hide the sub line, and grow back.
    const spy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('fb-w-area') ? 140 : 160
    })
    size = { w: 300, h: 160 }
    const { container } = renderWithApp(<FitWidget widget={{ ...base, sub: 'From the last port read', type: 'stat', value: 9, unit: '', tone: '' }} />)
    expect(container.querySelector('.fb-w')?.getAttribute('data-level')).toBe('m')
    expect(screen.getByText('From the last port read')).toBeInTheDocument()
    spy.mockImplementation(() => size.h)
  })
})
