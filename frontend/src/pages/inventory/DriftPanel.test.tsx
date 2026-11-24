import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DriftRow } from '@/api/inventoryDrift'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DriftPanel } from './DriftPanel'

afterEach(() => vi.unstubAllGlobals())

const rows: DriftRow[] = [
  { kind: 'field', field: 'model', configured: 'C9200', actual: 'C9300-48P', since: '2026-11-24T10:00:00Z' },
  { kind: 'hostname', field: 'name', configured: 'sw-a-01', actual: 'core-x' },
  { kind: 'interface', field: 'Gi1/0/9', configured: 'present', actual: 'missing' },
]

describe('DriftPanel', () => {
  it('lists what differs and takes the device value for a field (#918)', async () => {
    const api = fakeFetch({ 'POST /api/inventory/d1/drift/take': { id: 'd1', drift: [] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<DriftPanel deviceId="d1" rows={rows} canEdit />)
    const table = await screen.findByRole('table', { name: 'Differs from the device' })
    expect(within(table).getByText('C9300-48P')).toBeInTheDocument()
    expect(within(table).getByText('Interface Gi1/0/9')).toBeInTheDocument()
    expect(within(table).getByText('not there')).toBeInTheDocument()
    expect(within(table).getByText(/a new name moves its seats/)).toBeInTheDocument()
    // Only the field can be taken: not the hostname, not the interface.
    expect(within(table).getAllByRole('button', { name: /^Take the device's/ })).toHaveLength(1)
    fireEvent.click(within(table).getByRole('button', { name: "Take the device's Model" }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ field: 'model' }))
    expect(await screen.findByText(/Taken from the device/)).toBeInTheDocument()
  })

  it('shows no Take for those who may not edit', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<DriftPanel deviceId="d1" rows={rows} canEdit={false} />)
    await screen.findByRole('table', { name: 'Differs from the device' })
    expect(screen.queryByRole('button', { name: /^Take/ })).not.toBeInTheDocument()
  })
})
