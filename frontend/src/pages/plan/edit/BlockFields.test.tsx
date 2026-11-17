import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BlockFields } from './BlockFields'
import type { ItemRef } from './geometry'

afterEach(() => vi.unstubAllGlobals())

const data = { hall: 'main' } as SeatViewData
const item = { kind: 'block' as const, id: 'A' }

function fields(block: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', fakeFetch({
    'GET /api/seat-blocks?hall=main': [{ id: 'A', cols: 12, rows: 2, naming: 'rows', row_start: 'C', ...block }],
  }).fn)
  const onChange = vi.fn<(ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>>(() => Promise.resolve())
  renderWithApp(<BlockFields data={data} item={item} onChange={onChange} />)
  return onChange
}

describe('Seat block fields', () => {
  it('saves a new size on Enter as one step with the old value, and nothing when it did not change', async () => {
    const onChange = fields()
    const cols = await screen.findByLabelText('Seats per row')
    fireEvent.keyDown(cols, { key: 'Enter' })
    fireEvent.change(cols, { target: { value: '16' } })
    fireEvent.keyDown(cols, { key: 'Enter' })
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
    expect(onChange).toHaveBeenCalledWith(item, { cols: 12 }, { cols: 16 })
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
    await screen.findByLabelText('Seats per row')
    expect(screen.queryByLabelText('First row letter')).toBeNull()
  })

  it('adds a gap in the middle of the rows, one seat wide', async () => {
    const onChange = fields({ col_gaps: [] })
    const section = (await screen.findByText('Gaps in the rows')).closest('div')!.parentElement!
    fireEvent.click(within(section).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { col_gaps: [] }, { col_gaps: [{ after: 6, size: 1 }] }))
  })

  it('removes a gap, and adds a lane between rows two seats high', async () => {
    const onChange = fields({ col_gaps: [{ after: 4, size: 1.5 }], row_gaps: [] })
    fireEvent.click(await screen.findByRole('button', { name: 'Remove this gap' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { col_gaps: [{ after: 4, size: 1.5 }] }, { col_gaps: [] }))
    const lanes = screen.getByText('Lanes between rows').closest('div')!.parentElement!
    fireEvent.click(within(lanes).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { row_gaps: [] }, { row_gaps: [{ after: 1, size: 2 }] }))
  })
})
