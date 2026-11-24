import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PaneForm } from './PaneForm'
import { planPane } from './model'

const plan = {
  hall: 'h1', halls: [{ id: 'h1', name: 'Main hall' }], seats: {},
  drawing: {
    box: '0 0 1600 1000', cell: 32, marks: [],
    shapes: [{ id: 'b1', cx: 400, cy: 300, rotation: 0, w: 64, h: 64, name: '', rows: [],
      row_list: [{ id: 'r-c', name: 'C' }, { id: 'r-d', name: 'D' }],
      cells: [{ seat: 'C-1', x: -32, y: -32, rc: [0, 0] }, { seat: 'D-1', x: -32, y: 0, rc: [1, 0] }] }],
  },
}

afterEach(() => vi.unstubAllGlobals())

describe('a plan pane showing one row (#1078)', () => {
  it('picks the row from the hall, grouped by its block', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/plan': plan, 'GET /api/options/halls': { options: [] } }).fn)
    renderWithApp(<PaneForm pane={planPane({ area: { kind: 'row', id: 'r-d' } })} onChange={() => {}} />)
    expect(await screen.findByDisplayValue('D')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Row')).toBeInTheDocument()
  })
})
