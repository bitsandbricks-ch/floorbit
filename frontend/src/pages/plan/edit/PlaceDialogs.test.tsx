import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { type NewBlock, PlaceBlockDialog, PlaceMarkDialog } from './PlaceDialogs'

afterEach(() => vi.unstubAllGlobals())

function blockDialog(defaults: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', fakeFetch({
    'GET /api/config': { floorplan_defaults: defaults },
    // Rows A and B are taken, so a new block starts at C.
    'GET /api/seat-blocks': [{ naming: 'rows', row_start: 'A', rows: 2, name: 'A' }],
  }).fn)
  const onCreate = vi.fn<(block: NewBlock, copies: { count: number; dx: number; dy: number } | null) => Promise<void>>(() => Promise.resolve())
  renderWithApp(<PlaceBlockDialog opened onClose={() => {}} onCreate={onCreate} />)
  return onCreate
}

describe('New seat block dialog', () => {
  it('starts at the next free row letter and says how many seats it makes', async () => {
    blockDialog()
    // A run of two rows by default (#1547).
    expect(await screen.findByText('16 seats, from row C, each row numbered 1 to 8')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Seats per row'), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: '3' } })
    expect(screen.getByText('30 seats, from row C, each row numbered 1 to 10')).toBeInTheDocument()
  })

  it('creates one block with the defaults from the settings', async () => {
    const onCreate = blockDialog({ row_labels: 'end', reverse_numbers: true })
    fireEvent.change(await screen.findByLabelText('Block name'), { target: { value: ' Gaming ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create block' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1))
    expect(onCreate).toHaveBeenCalledWith({
      naming: 'rows', row_start: 'C', row_labels: 'end', name: 'Gaming', cols: 8, rows: 2,
      numbering_pattern: 'blockname_number', reverse_numbers: true, rotation: 0, spacer: 1,
    }, null)
  })

  it('puts the spacer between the rows, and none in a single row', async () => {
    const onCreate = blockDialog()
    fireEvent.change(await screen.findByLabelText('Spacer between rows'), { target: { value: '0.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create block' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1))
    expect(onCreate.mock.calls[0][0]).toMatchObject({ rows: 2, spacer: 0.5 })
    fireEvent.change(screen.getByLabelText('Rows'), { target: { value: '1' } })
    expect(screen.queryByLabelText('Spacer between rows')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Create block' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(2))
    expect(onCreate.mock.calls[1][0]).toMatchObject({ rows: 1, spacer: 0 })
  })

  it('makes copies below each other, spaced by the gap from the settings', async () => {
    const onCreate = blockDialog({ block_gap: 5 })
    fireEvent.change(await screen.findByLabelText('How many blocks'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create 3 blocks' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1))
    // Two rows of 8 and a one-seat spacer: 3 x 3.2 % tall plus 1.6 % room, plus the 5 % gap.
    expect(onCreate.mock.calls[0][1]).toEqual({ count: 3, dx: 0, dy: expect.closeTo(16.2, 5) })
  })

  it('names seats after the block when asked to', async () => {
    blockDialog({ naming: 'block' })
    fireEvent.change(await screen.findByLabelText('Block name'), { target: { value: 'D' } })
    expect(screen.getByText('16 seats: D-1 to D-16')).toBeInTheDocument()
  })
})

describe('New label dialog', () => {
  it('places trimmed text at the chosen size, and not while it is empty', async () => {
    const onCreate = vi.fn(() => Promise.resolve())
    renderWithApp(<PlaceMarkDialog kind="text" onClose={() => {}} onCreate={onCreate} />)
    const place = await screen.findByRole('button', { name: 'Place' })
    expect(place).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/^Text/), { target: { value: '  Stage  ' } })
    fireEvent.click(screen.getByText('Large'))
    fireEvent.click(place)
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith({ kind: 'text', text: 'Stage', size: 'l' }))
  })
})
