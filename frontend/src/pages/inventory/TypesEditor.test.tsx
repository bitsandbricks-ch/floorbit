import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InventoryOverview, InventoryType } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { TypesEditor } from './TypesEditor'

afterEach(() => vi.unstubAllGlobals())

const rack: InventoryType = {
  id: 'rack', name: 'Rack', sort: 'stored', builtin: false, icon: '', default_icon: 'other', color: '',
  fields: [], own_fields: [], properties: {}, features: {}, count: 0,
}
const overview = { groups: [], tags: [], icons: ['other'], custom_icons: [] } as unknown as InventoryOverview

describe('Types editor', () => {
  it('saves a type with the shared save bar (#993)', async () => {
    const api = fakeFetch({ 'GET /api/inventory/types': { types: [rack], field_kinds: [] }, 'PATCH /api/inventory/types/rack': { ...rack, name: 'Racks' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<TypesEditor opened overview={overview} start="rack" onClose={() => {}} />)
    const name = await screen.findByRole('textbox', { name: 'Name' })
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    fireEvent.change(name, { target: { value: 'Racks' } })
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(name).toHaveValue('Rack')
    fireEvent.change(name, { target: { value: 'Racks' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'Racks' }))
  })
})
