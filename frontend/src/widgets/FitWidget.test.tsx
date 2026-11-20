import { act, fireEvent, screen } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import type { Widget } from '@/api/types'
import { renderWithApp } from '@/test/render'
import { clock } from '@/lib/time'
import { FitWidget } from './FitWidget'
import { LevelReport } from './levelReport'
import { AutoPage } from './autoPage'

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

  it('tells the dashboard editor the level it drew at', () => {
    size = { w: 300, h: 140 }
    const report = { level: vi.fn(), rows: vi.fn() }
    renderWithApp(<LevelReport.Provider value={report}><FitWidget widget={status} /></LevelReport.Provider>)
    expect(report.level).toHaveBeenLastCalledWith('m', false)
    // 4 of the 30 rows fit; the editor says so before the screen shows "+26 more".
    expect(report.rows).toHaveBeenLastCalledWith(4, 30)
  })

  it('tells the editor when the box is too small even for small', () => {
    size = { w: 90, h: 40 }
    const report = { level: vi.fn(), rows: vi.fn() }
    renderWithApp(<LevelReport.Provider value={report}><FitWidget widget={status} /></LevelReport.Provider>)
    expect(report.level).toHaveBeenLastCalledWith('s', true)
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

  it('turns the pages of a large list by itself on a wall, unless someone points at it', () => {
    vi.useFakeTimers()
    try {
      size = { w: 700, h: 300 }
      const table: Widget = { ...base, type: 'table', columns: [{ key: 'n', label: 'N' }],
        rows: Array.from({ length: 40 }, (_, i) => ({ n: `row ${i + 1}` })) }
      const { container } = renderWithApp(<AutoPage.Provider value={10}><FitWidget widget={table} /></AutoPage.Provider>)
      expect(screen.getByText('row 1')).toBeInTheDocument()
      act(() => { vi.advanceTimersByTime(10_000) })
      expect(screen.queryByText('row 1')).not.toBeInTheDocument()
      fireEvent.pointerEnter(container.querySelector('.fb-w-rows')!)
      const page = screen.getByText(/ of 40/).textContent
      act(() => { vi.advanceTimersByTime(30_000) })
      expect(screen.getByText(/ of 40/).textContent).toBe(page)
    } finally {
      vi.useRealTimers()
    }
  })

  it('draws a series as a graph with a legend', () => {
    size = { w: 600, h: 300 }
    const series: Widget = { ...base, type: 'series', unit: 'bit/s', series: [
      { label: 'Download', points: [[1800000000, 1e9], [1800000060, 2e9]] }, { label: 'Upload', points: [[1800000000, 1e8], [1800000060, 2e8]] }] }
    renderWithApp(<FitWidget widget={series} />)
    expect(screen.getByRole('img', { name: 'Graph: W' })).toBeInTheDocument()
    expect(screen.getByText('2 Gbit/s')).toBeInTheDocument()
  })

  it('writes the time axis in the samples own times', () => {
    size = { w: 900, h: 500 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 1], [1800003600, 2]] }] }
    const { container, unmount } = renderWithApp(<FitWidget widget={series} />)
    const axis = [...container.querySelectorAll('.fb-w-axis span')].map((s) => s.textContent)
    expect(axis[0]).toBe(clock(1800000000))
    expect(axis[2]).toBe(clock(1800003600))
    unmount()
    const cols = renderWithApp(<FitWidget widget={series} pick="column" />)
    expect(cols.container.querySelector('.fb-w-axis span')?.textContent).toBe(clock(1800000000))
  })

  it('keeps a fixed axis top a pane sets', () => {
    size = { w: 900, h: 500 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 1], [1800003600, 2]] }] }
    const { container } = renderWithApp(<FitWidget widget={series} look={{ axis: { min: 1, max: 1000, log: true } }} />)
    expect(container.querySelectorAll('.fb-w-axis span')[1].textContent).toContain('1,000')
  })

  it('draws a comparison line dotted, over the time the real lines cover', () => {
    size = { w: 900, h: 500 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 1], [1800003600, 2]] },
      { label: 'Yesterday', ghost: true, points: [[1799990000, 9], [1800000000, 3], [1800003600, 4]] }] }
    const { container } = renderWithApp(<FitWidget widget={series} />)
    expect(container.querySelectorAll('.fb-w-ghost')).toHaveLength(1)
    expect(container.querySelector('.fb-w-ghost')!.getAttribute('points')!.split(' ')).toHaveLength(2)
    expect(screen.getByText('Yesterday')).toBeInTheDocument()
  })

  it('marks what happened with a line, named under the pointer', () => {
    size = { w: 900, h: 500 }
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Down', points: [[1800000000, 1], [1800003600, 2]] }],
      marks: [{ t: 1800003600, label: 'sw-a1 down', tone: 'err' }, { t: 1700000000, label: 'Too early', tone: '' }] }
    const { container } = renderWithApp(<FitWidget widget={series} />)
    expect(container.querySelectorAll('.fb-w-mark')).toHaveLength(1)
    expect(container.querySelector('.fb-w-mark')!.getAttribute('class')).toContain('fb-tone-err')
    const plot = container.querySelector('.fb-w-plot')!
    plot.getBoundingClientRect = () => ({ left: 0, top: 0, right: 900, bottom: 400, width: 900, height: 400, x: 0, y: 0, toJSON: () => ({}) })
    fireEvent.pointerMove(plot, { clientX: 899 })
    expect(screen.getByText('sw-a1 down')).toBeInTheDocument()
    expect(screen.queryByText('Too early')).toBeNull()
  })

  it('puts a stat\'s history under it, with how it moved, when the pane asks', () => {
    size = { w: 300, h: 220 }
    const t0 = 1800000000
    const series: Widget = { ...base, type: 'series', unit: '', series: [{ label: 'Clients', points: [[t0, 40], [t0 + 1800, 50], [t0 + 5400, 60]] }] }
    const { container } = renderWithApp(<FitWidget widget={series} pick="stat" pin="m" look={{ spark: true, change: true, text: 'l' }} />)
    expect(container.querySelector('.fb-w-spark polyline')).not.toBeNull()
    expect(container.querySelector('.fb-w-change')!.textContent).toBe('▲ 20 % vs an hour ago')
    expect(container.querySelector('.fb-w-text-l')).not.toBeNull()
  })

  it('says why a small stat has nothing to show', () => {
    size = { w: 160, h: 90 }
    renderWithApp(<FitWidget widget={{ ...base, type: 'stat', value: '–', unit: '', tone: '', sub: 'No LAN cache set up' }} pin="s" />)
    expect(screen.getByText('No LAN cache set up')).toBeInTheDocument()
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

  it('writes a big pie total short, so it fits the ring', () => {
    size = { w: 500, h: 220 }
    const mix: Widget = { ...base, type: 'list', items: [{ label: 'Web', value: '360 GB', tone: '', number: 3.6e11 },
      { label: 'Gaming', value: '183 GB', tone: '', number: 1.83e11 }] }
    renderWithApp(<FitWidget widget={mix} pick="pie" look={{ number: { decimals: undefined, short: undefined } }} />)
    expect(screen.getByText('543G')).toBeInTheDocument()
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
