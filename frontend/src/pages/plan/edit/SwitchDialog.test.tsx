import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PlaceSwitchDialog, type InventorySwitch } from './SwitchDialog'

afterEach(() => vi.unstubAllGlobals())

const sw = (id: string, placed = false, source = 'netbox'): InventorySwitch => ({ id, name: id, placed, source })

function dialog(list: InventorySwitch[]) {
  vi.stubGlobal('fetch', fakeFetch({ 'GET /api/switches': list }).fn)
  const onPlace = vi.fn(() => Promise.resolve(true))
  renderWithApp(<PlaceSwitchDialog opened onClose={() => {}} onPlace={onPlace} />)
  return onPlace
}

describe('Place switch dialog', () => {
  it('offers only inventory switches not on a plan yet, and places the ticked ones together', async () => {
    const onPlace = dialog([sw('sw-a-01'), sw('sw-a-02'), sw('sw-b-01', true), sw('SW-01', false, 'manual')])
    const list = await screen.findByRole('list', { name: 'Switches not on a plan yet' })
    expect(list.textContent).toBe('sw-a-01sw-a-02')
    expect(screen.getByRole('button', { name: 'Place switch' })).toBeDisabled()
    fireEvent.click(screen.getByLabelText('sw-a-01'))
    fireEvent.click(screen.getByLabelText('sw-a-02'))
    fireEvent.click(screen.getByRole('button', { name: 'Place 2 switches' }))
    await waitFor(() => expect(onPlace).toHaveBeenCalledWith({ ids: ['sw-a-01', 'sw-a-02'] }))
  })

  it('filters the list by name, and says when nothing matches', async () => {
    dialog([sw('sw-a-01'), sw('core-01')])
    const filter = await screen.findByPlaceholderText('Filter by name')
    fireEvent.change(filter, { target: { value: 'CORE' } })
    expect(screen.getByRole('list', { name: 'Switches not on a plan yet' }).textContent).toBe('core-01')
    fireEvent.change(filter, { target: { value: 'zz' } })
    expect(screen.getByText('No switch left to place matches the filter.')).toBeInTheDocument()
  })

  it('starts on a new switch with the next free name when the inventory has none left', async () => {
    const onPlace = dialog([sw('sw-a-01', true), sw('SW-01', true, 'manual')])
    const name = await screen.findByLabelText(/^Name/)
    expect(name).toHaveValue('SW-02')
    fireEvent.change(name, { target: { value: '  lab-01 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add switch' }))
    await waitFor(() => expect(onPlace).toHaveBeenCalledWith({ name: 'lab-01' }))
  })
})
