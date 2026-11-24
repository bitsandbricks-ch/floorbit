import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FirewallList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { RangePanel } from './RangePanel'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const range = {
  id: 'r1', cidr: '192.0.2.0/26', name: 'Block A', firewalls: ['fw-01', 'fw-02'], fallback: [], state: 'primary' as const, seats: 40,
  source: 'import' as const, plugin: 'netbox', switches: ['g-green'],
  parts: [{ cidr: '192.0.2.0/27', firewall: 'fw-01', now: 'fw-01', state: 'primary' as const, seats: 22 },
    { cidr: '192.0.2.32/27', firewall: 'fw-02', now: 'fw-02', state: 'primary' as const, seats: 18 }],
}
const list: FirewallList = {
  firewalls: [{ id: 'f1', name: 'fw-01', model: '', hall: '', status: 'online', serving: [], planned: [], taken_over: [], seats: 22 },
    { id: 'f2', name: 'fw-02', model: '', hall: '', status: 'online', serving: [], planned: [], taken_over: [], seats: 18 }],
  ranges: [range], counts: { firewalls: 2, down: 0, failover: 0, without: 0 }, unread: false,
}

// A range is changed on its own inventory page, no longer in a dialog on Firewalls (#1312).
describe('RangePanel', () => {
  it('shows each part and lets the crew set an imported range\'s switches with the save bar', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': list,
      'GET /api/inventory/groups': { groups: [{ id: 'g-green', name: 'Green' }, { id: 'g-red', name: 'Red' }], tags: [] },
      'GET /api/inventory': { devices: [{ id: 'd1', name: 'sw-r1', role: 'switch' }], sources: [] },
      'PUT /api/firewalls/ranges/r1': { body: { ...range, switches: ['g-green', 'd1'] } },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<RangePanel id="r1" canEdit />)
    expect(await screen.findByText('192.0.2.32/27')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Range' })).toBeDisabled()     // from NetBox
    const [pick] = screen.getAllByLabelText('Switches and switch groups').filter((el) => el.tagName === 'INPUT' && el.getAttribute('type') !== 'hidden')
    fireEvent.click(pick)
    fireEvent.click(await screen.findByRole('option', { name: 'sw-r1', hidden: true }))
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ switches: ['g-green', 'd1'] }))
  })

  it('starts a plan on a prefix that no firewall routes yet (IPAM, #1346)', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': list,
      'GET /api/inventory/groups': { groups: [], tags: [] }, 'GET /api/inventory': { devices: [], sources: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<RangePanel id="p9" canEdit prefix="198.51.100.0/24" />)
    expect(await screen.findByText('No firewalls route this prefix yet.')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Range' })).toHaveValue('198.51.100.0/24')
  })

  it('shows nothing for a prefix without a plan to those who may not edit', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/firewalls': list })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<RangePanel id="p9" canEdit={false} prefix="198.51.100.0/24" />)
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/firewalls')).toBe(true))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('No firewalls route this prefix yet.')).toBeNull()
  })

})
