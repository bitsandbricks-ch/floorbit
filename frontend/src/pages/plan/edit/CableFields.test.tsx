import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BlockFields } from './BlockFields'
import type { ItemRef } from './geometry'
import type { BlockRow } from './rows'

afterEach(() => vi.unstubAllGlobals())

const data = { hall: 'main' } as SeatViewData
const item = { kind: 'block' as const, id: 'A' }
const row = (id: string, more: Partial<BlockRow> = {}): BlockRow =>
  ({ id, seats: 8, shape: 'line', gap: 0, align: 'start', shift: 0, side: '', reverse: false, col_gaps: [], ...more })
const A = row('1'), B = row('2', { gap: 0.5 })

function fields(section: 'block' | 'rows') {
  vi.stubGlobal('fetch', fakeFetch({ 'GET /api/seat-blocks?hall=main': [{ id: 'A', rows: [A, B], naming: 'rows' }] }).fn)
  const onChange = vi.fn<(ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>>(() => Promise.resolve())
  renderWithApp(<BlockFields data={data} item={item} onChange={onChange} section={section} />)
  return onChange
}

describe('Seat cables and chairs (issue #1342)', () => {
  it('sets the chairs of a table pair on its outer sides', async () => {
    const onChange = fields('block')
    fireEvent.click(await screen.findByRole('button', { name: 'Set chairs automatically' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [A, B] },
      { rows: [{ ...A, side: 'left' }, { ...B, side: 'right' }] }))
  })

  it('sets where the cables plug in for all rows, or for one', async () => {
    const onChange = fields('block')
    fireEvent.click(await screen.findByText('Chair side'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [A, B] },
      { rows: [{ ...A, cables: 'chair' }, { ...B, cables: 'chair' }] }))
  })

  it('sets one row behind its table', async () => {
    const onChange = fields('rows')
    fireEvent.click(await screen.findByText('Behind'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(item, { rows: [A, B] }, { rows: [{ ...A, cables: 'behind' }, B] }))
  })
})
