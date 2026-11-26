import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Reads, SourceConflict } from '@/api/discoverySources'
import { fakeFetch, renderWithApp } from '@/test/render'
import { ConflictPanel } from './ConflictPanel'
import ReadsPage from './ReadsPage'

afterEach(() => vi.unstubAllGlobals())

const sources = [{ id: 'monitoring', name: 'Built-in telemetry' }, { id: 'opnsense', name: 'OPNsense' }]
const reads: Reads = {
  role: 'firewall', devices: 2, monitoring: 'Built-in telemetry',
  rows: [
    { area: 'identity', name: 'Model, serial and software', builtin: true, sources, deciding: 'monitoring', why: 'default',
      minutes: 60, action: 'identity', goes_to: 'fields', last: { at: '2026-11-25T18:02:00Z', devices: 2, changed: 0 }, conflicts: 1 },
    { area: 'routes', name: 'Routes', builtin: true, sources, deciding: 'opnsense', why: 'admin',
      minutes: 15, action: 'opnsense.routes', goes_to: 'discovered.routes', last: null, conflicts: 0 },
    { area: 'gateways', name: 'Gateways', builtin: false, sources: [sources[1]], deciding: 'opnsense', why: 'only',
      minutes: 5, action: 'opnsense.gateways', goes_to: 'auto.gateways.*', last: null, conflicts: 0 },
  ],
}
const admin = { enabled: true, user: { name: 'admin', permissions: ['settings.manage', 'floorplan.edit'] } }

describe('ReadsPage', () => {
  it('lists each area with its deciding source, and an admin picks another (#965)', async () => {
    const api = fakeFetch({ 'GET /api/inventory/discovery/types/firewall': reads, 'GET /api/auth/me': admin,
      'PUT /api/inventory/discovery/deciding': reads })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Routes><Route path="/inventory/reads/:role" element={<ReadsPage />} /></Routes>, '/inventory/reads/firewall')
    expect(await screen.findByRole('heading', { name: 'What Floorbit reads: Firewall' })).toBeInTheDocument()
    const routes = (await screen.findByText('Routes')).closest('tr') as HTMLElement
    expect(within(routes).getByText('picked by an admin')).toBeInTheDocument()
    expect(within(routes).getByText('discovered.routes')).toBeInTheDocument()
    const gateways = screen.getByText('Gateways').closest('tr') as HTMLElement
    expect(within(gateways).getByText('only source')).toBeInTheDocument()
    expect(within(gateways).queryByLabelText(/^Deciding source/)).not.toBeInTheDocument()
    expect(screen.getByText('1 field')).toBeInTheDocument()
    const identity = screen.getByText('Identity').closest('tr') as HTMLElement
    const pick = await within(identity).findByLabelText('Deciding source for Model, serial and software on Firewall')
    fireEvent.click(pick)
    const list = await waitFor(() => {
      const el = document.getElementById(pick.getAttribute('aria-controls') ?? '')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    fireEvent.click(within(list).getByRole('option', { name: 'OPNsense', hidden: true }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body)
      .toEqual({ role: 'firewall', area: 'identity', source: 'opnsense' }))
  })
})

describe('ConflictPanel', () => {
  const rows: SourceConflict[] = [{ kind: 'conflict', field: 'os', why: 'default', since: '2026-11-25T18:02:00Z',
    deciding: { source: 'monitoring', name: 'Built-in telemetry', value: '24.7.9' },
    other: { source: 'opnsense', name: 'OPNsense', value: '24.7.10' } }]

  it('shows both values like a diff and takes the other source\'s value', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': admin, 'POST /api/inventory/d1/conflicts/take': { id: 'd1' },
      'PUT /api/inventory/discovery/deciding': reads })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<ConflictPanel deviceId="d1" role="firewall" rows={rows} canEdit />)
    const hunk = await screen.findByRole('group', { name: 'Operating system' })
    expect(hunk.querySelector('.is-del')).toHaveTextContent('24.7.9 (Built-in telemetry, deciding)')
    expect(hunk.querySelector('.is-add')).toHaveTextContent('24.7.10 (OPNsense)')
    fireEvent.click(within(hunk).getByRole('button', { name: "Take OPNsense's value" }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ field: 'os', source: 'opnsense' }))
    fireEvent.click(await within(hunk).findByRole('button', { name: 'Make OPNsense decide identity on: Firewall' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body)
      .toEqual({ role: 'firewall', area: 'identity', source: 'opnsense' }))
    expect(screen.getByRole('link', { name: 'What Floorbit reads: Firewall' })).toHaveAttribute('href', '/inventory/reads/firewall')
  })
})
