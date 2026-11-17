import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { notifications } from '@mantine/notifications'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { HallsDialog } from './HallsDialog'

afterEach(() => { vi.unstubAllGlobals(); notifications.clean() })

const hall = (id: string, name: string, extra = {}) => ({ id, name, background: null, switches: 0, seat_blocks: 0, ...extra })

function dialog(routes: Record<string, unknown> = {}, current = 'main') {
  const api = fakeFetch({ 'GET /api/halls': { halls: [hall('main', 'Main hall', { switches: 3, seat_blocks: 2 }), hall('side', 'Side room')] }, ...routes })
  vi.stubGlobal('fetch', api.fn)
  const onOpen = vi.fn()
  const onClose = vi.fn()
  const onChanged = vi.fn(() => Promise.resolve())
  renderWithApp(<HallsDialog opened current={current} onClose={onClose} onOpen={onOpen} onChanged={onChanged} />)
  const sent = (method: string) => api.calls.filter((c) => c.method === method)
  return { api, onOpen, onClose, onChanged, sent }
}

describe('Halls dialog', () => {
  it('adds a hall by name, trimmed, and says so', async () => {
    const d = dialog({ 'POST /api/halls': { id: 'tent', name: 'Tent' } })
    const input = await screen.findByLabelText('New hall')
    fireEvent.change(input, { target: { value: '  Tent ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add hall' }))
    await waitFor(() => expect(d.sent('POST')).toHaveLength(1))
    expect(d.sent('POST')[0].body).toEqual({ name: 'Tent' })
    expect(await screen.findByText('Added Tent')).toBeInTheDocument()
    await waitFor(() => expect(input).toHaveValue(''))
    expect(d.onChanged).toHaveBeenCalled()
  })

  it('renames on Enter, and sends nothing when the name did not change', async () => {
    const d = dialog({ 'PUT /api/halls/side': { ok: true } })
    const name = await screen.findByDisplayValue('Side room')
    fireEvent.keyDown(name, { key: 'Enter' })
    fireEvent.change(name, { target: { value: 'Side room 2' } })
    fireEvent.keyDown(name, { key: 'Enter' })
    await waitFor(() => expect(d.sent('PUT')).toHaveLength(1))
    expect(d.sent('PUT')[0]).toMatchObject({ path: '/api/halls/side', body: { name: 'Side room 2' } })
  })

  it('opens another hall, and shows the current one as shown', async () => {
    const d = dialog()
    await screen.findByDisplayValue('Side room')
    expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(d.onOpen).toHaveBeenCalledWith('side')
    expect(d.onClose).toHaveBeenCalled()
  })

  it('deletes the hall that is shown after asking, and moves to the other one', async () => {
    const d = dialog({ 'DELETE /api/halls/main': { ok: true } })
    await screen.findByDisplayValue('Main hall')
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])
    const ask = await screen.findByRole('dialog', { name: 'Delete' })
    expect(within(ask).getByText(/Delete Main hall\?/)).toBeInTheDocument()
    fireEvent.click(within(ask).getByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(d.sent('DELETE')).toHaveLength(1))
    expect(d.sent('DELETE')[0].path).toBe('/api/halls/main')
    await waitFor(() => expect(d.onOpen).toHaveBeenCalledWith('side'))
  })

  it('shows what the server refused, line by line, when a CSV import fails', async () => {
    const d = dialog({ 'POST /api/halls/main/seat-blocks.csv': () => ({ status: 400, body: { error: 'Bad CSV', errors: [{ line: 2, error: 'cols must be a number' }, { error: 'no name column' }] } }) })
    await screen.findByDisplayValue('Main hall')
    const file = new File(['name,x\nA,zz\n'], 'blocks.csv', { type: 'text/csv' })
    const inputs = document.querySelectorAll<HTMLInputElement>('input[type=file][accept=".csv,text/csv"]')
    fireEvent.change(inputs[0], { target: { files: [file] } })
    expect(await screen.findByText('Nothing was imported')).toBeInTheDocument()
    expect(screen.getByText('line 2: cols must be a number · no name column')).toBeInTheDocument()
    expect(d.sent('POST')[0].body).toEqual({ csv: 'name,x\nA,zz\n' })
  })
})
