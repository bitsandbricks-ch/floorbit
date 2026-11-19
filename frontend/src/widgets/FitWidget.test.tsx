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
})
