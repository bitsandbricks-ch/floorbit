import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DriftRow } from '@/api/inventoryDrift'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DriftAll, DriftPanel } from './DriftPanel'

afterEach(() => vi.unstubAllGlobals())

const rows: DriftRow[] = [
  { kind: 'field', field: 'model', configured: 'C9200', actual: 'C9300-48P', since: '2026-11-24T10:00:00Z' },
  { kind: 'hostname', field: 'name', configured: 'sw-a-01', actual: 'core-x' },
  { kind: 'interface', field: 'Gi1/0/9', configured: 'present', actual: 'missing' },
]

describe('DriftPanel', () => {
  it('shows each difference as a diff hunk and takes the device value for a field (#918, #903)', async () => {
    const api = fakeFetch({ 'POST /api/inventory/d1/drift/take': { id: 'd1', drift: [] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<DriftPanel deviceId="d1" rows={rows} canEdit />)
    // Grouped like the files of a diff: fields, then name and address, then interfaces.
    const sections = await screen.findAllByRole('region')
    expect(sections.map((s) => s.getAttribute('aria-label'))).toEqual(['Fields', 'Name and address', 'Interfaces'])
    const model = screen.getByRole('group', { name: 'Model' })
    expect(model.querySelector('.is-del')).toHaveTextContent('Inventory: C9200')
    expect(model.querySelector('.is-add')).toHaveTextContent('Device says: C9300-48P')
    const iface = screen.getByRole('group', { name: 'Interface Gi1/0/9' })
    expect(within(iface).getByText('not there')).toBeInTheDocument()
    expect(screen.getByText(/a new name moves its seats/)).toBeInTheDocument()
    // Only the field can be taken: not the hostname, not the interface.
    expect(screen.getAllByRole('button', { name: /^Take the device's/ })).toHaveLength(1)
    fireEvent.click(within(model).getByRole('button', { name: "Take the device's Model" }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ field: 'model' }))
    expect(await screen.findByText(/Taken from the device/)).toBeInTheDocument()
  })

  it('shows no Take for those who may not edit', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<DriftPanel deviceId="d1" rows={rows} canEdit={false} />)
    await screen.findByRole('group', { name: 'Model' })
    expect(screen.queryByRole('button', { name: /^Take/ })).not.toBeInTheDocument()
  })

  it('lists every device that differs, each linking to its page', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<DriftAll devices={[{ id: 'd1', name: 'sw-a-01', drift: rows }]} canEdit={false} />)
    expect(await screen.findByRole('link', { name: 'sw-a-01' })).toHaveAttribute('href', '/inventory/devices/d1')
    expect(screen.getByText('3 differences')).toBeInTheDocument()
  })

  it('says so when nothing differs', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<DriftAll devices={[]} canEdit />)
    expect(await screen.findByText('Every device matches the inventory.')).toBeInTheDocument()
  })
})
