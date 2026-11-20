import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InventoryEntry, InventoryType } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { BoolCell } from './BoolCell'

afterEach(() => vi.unstubAllGlobals())

const field = { key: 'lookups', label: 'Check-in lookups', default: 'no' }
const type = { id: 'vlan', name: 'VLAN or IP range', sort: 'stored' } as InventoryType
const entry = { id: 'e1', name: 'Seats', fields: { vlan_id: '110', prefix: '192.0.2.0/24' } } as unknown as InventoryEntry

describe('BoolCell', () => {
  it('turns check-in lookups on for one range right in the list', async () => {
    const api = fakeFetch({ 'PATCH /api/inventory/entries/vlan/e1': { ...entry, fields: { ...entry.fields, lookups: 'yes' } } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<BoolCell type={type} entry={entry} field={field} canEdit />)
    const toggle = await screen.findByRole('switch', { name: 'Check-in lookups: Seats' })
    expect(toggle).not.toBeChecked()
    fireEvent.click(toggle)
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ fields: { lookups: true } }))
  })

  it('only says yes or no to who may not edit', async () => {
    renderWithApp(<BoolCell type={type} entry={{ ...entry, fields: { lookups: 'yes' } }} field={field} canEdit={false} />)
    expect(await screen.findByText('Yes')).toBeInTheDocument()
    expect(screen.queryByRole('switch')).toBeNull()
  })
})
