import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { pick } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BlockFields } from './BlockFields'
import type { ItemRef } from './geometry'
import type { BlockRow } from './rows'

afterEach(() => vi.unstubAllGlobals())

const data = { hall: 'main' } as SeatViewData
const item = { kind: 'block' as const, id: 'A' }
const row = (id: string, seats = 12, more: Partial<BlockRow> = {}): BlockRow =>
  ({ id, seats, shape: 'line', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [], ...more })
const C = row('1'), D = row('2', 12, { gap: 2 })

function fields(block: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', fakeFetch({
    'GET /api/seat-blocks?hall=main': [{ id: 'A', rows: [C, D], row_names: ['C', 'D'], naming: 'rows', row_start: 'C', ...block }],
  }).fn)
  const onChange = vi.fn<(ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>>(() => Promise.resolve())
  renderWithApp(<BlockFields data={data} item={item} onChange={onChange} />)
  return onChange
}

describe('Seat block fields', () => {
  it('lists the rows with the space above each, and adds a row as long as the last', async () => {
    const onChange = fields()
    expect(await screen.findByText('2 rows')).toBeInTheDocument()
    expect(screen.getByLabelText('Space above row D, in seats')).toHaveValue('2 seats')
    fireEvent.click(screen.getByRole('button', { name: 'Add row' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [C, D, row('3')] }))
  })

  it('moves a row down and takes one out, the ids staying with their rows', async () => {
    const onChange = fields()
    fireEvent.click(await screen.findByRole('button', { name: 'Move row C down' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [D, C] }))
    fireEvent.click(screen.getByRole('button', { name: 'Take out row C' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [D] }))
  })

  it('changes one row: its seats on Enter, and a U shape with seats on three sides', async () => {
    const onChange = fields()
    fireEvent.click(await screen.findByRole('button', { name: 'Row D: change it' }))
    const seats = await screen.findByLabelText('Seats')
    fireEvent.change(seats, { target: { value: '16' } })
    fireEvent.keyDown(seats, { key: 'Enter' })
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [C, { ...D, seats: 16 }] }))
    await pick('Shape', 'U')
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [C, { ...D, shape: 'u', sides: [3, 6, 3] }] }))
  })

  it('takes letters only for the first row, in capitals', async () => {
    const onChange = fields()
    const start = await screen.findByLabelText('First row letter')
    fireEvent.change(start, { target: { value: 'd1' } })
    expect(start).toHaveValue('d')
    fireEvent.blur(start)
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { row_start: 'C' }, { row_start: 'D' }))
  })

  it('hides the row letter fields when seats are named after the block', async () => {
    fields({ naming: 'block' })
    await screen.findByText('2 rows')
    expect(screen.queryByLabelText('First row letter')).toBeNull()
  })

  it('adds a gap in the middle of a row, one seat wide', async () => {
    const onChange = fields()
    fireEvent.click(await screen.findByRole('button', { name: 'Row C: change it' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Add a gap after seat 6' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [C, D] }, { rows: [{ ...C, col_gaps: [{ after: 6, size: 1 }] }, D] }))
  })
})
