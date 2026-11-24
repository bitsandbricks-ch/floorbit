import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FirewallList, InventoryEntry, InventoryType } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { IpamView } from './IpamView'
import { ipNum } from './ipam'

afterEach(() => vi.unstubAllGlobals())

const type = (id: string, name: string): InventoryType => ({
  id, name, sort: 'stored', builtin: true, icon: '', default_icon: 'vlan', color: '', fields: [], own_fields: [],
  properties: {}, features: {}, count: 0,
})
const entry = (id: string, type: string, name: string, fields: Record<string, string>, sources: string[] = []): InventoryEntry => ({
  id, type, name, summary: '', detail: '', link: '', group_id: null, tags: [], properties: {}, icon: '', color: '', notes: '',
  fields, sources, gone: [],
})
const vlans = [entry('v10', 'vlan', 'Seats A', { vlan_id: '10', purpose: 'Seats' }, ['netbox']),
  entry('v20', 'vlan', 'Crew', { vlan_id: '20', purpose: 'Crew' })]
const prefixes = [
  entry('p1', 'prefix', 'Seats A', { prefix: '192.0.2.0/24', vlan_id: '10', purpose: 'Seats' }, ['netbox']),
  entry('p2', 'prefix', '198.51.100.0/25', { prefix: '198.51.100.0/25', vlan_id: '20', purpose: 'Crew' }),
]
const fw: FirewallList = {
  firewalls: [], unread: false, counts: { firewalls: 0, down: 0, failover: 1, without: 0 },
  ranges: [{ id: 'p1', cidr: '192.0.2.0/24', name: 'Seats A', firewalls: ['fw-1', 'fw-2'], fallback: [], parts: [], state: 'failover', seats: 0 }],
}
const api = () => fakeFetch({
  'GET /api/inventory/entries?type=vlan': { entries: vlans },
  'GET /api/inventory/entries?type=prefix': { entries: prefixes },
  'GET /api/firewalls': fw,
})
const types = [type('vlan', 'VLAN'), type('prefix', 'Prefix or range')]
const names = (id: string) => ({ netbox: 'NetBox' }[id] ?? id)

describe('IpamView (#1346)', () => {
  it('lists prefixes with their VLAN, firewalls and how the route is doing', async () => {
    vi.stubGlobal('fetch', api().fn)
    renderWithApp(<IpamView types={types} sub="prefixes" onSub={() => {}} canEdit sourceName={names} />)
    const row = (await screen.findByRole('link', { name: '192.0.2.0/24' })).closest('tr')!
    expect(within(row).getByRole('link', { name: '10 · Seats A' })).toHaveAttribute('href', '/inventory/entries/vlan/v10')
    expect(within(row).getByText('fw-1, fw-2')).toBeInTheDocument()
    expect(within(row).getByText('On its fallback')).toBeInTheDocument()
    expect(within(row).getByText('NetBox')).toBeInTheDocument()
    // Only prefixes with firewalls.
    fireEvent.click(screen.getByRole('switch', { name: 'With firewalls' }))
    expect(screen.queryByRole('link', { name: '198.51.100.0/25' })).toBeNull()
    expect(screen.getByText('1 prefix')).toBeInTheDocument()
  })

  it('lists VLANs with the prefixes in them', async () => {
    vi.stubGlobal('fetch', api().fn)
    renderWithApp(<IpamView types={types} sub="vlans" onSub={() => {}} canEdit={false} sourceName={names} />)
    const row = (await screen.findByRole('link', { name: 'Crew' })).closest('tr')!
    expect(within(row).getByRole('link', { name: '198.51.100.0/25' })).toHaveAttribute('href', '/inventory/entries/prefix/p2')
    expect(within(row).getByText('By hand')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add VLAN' })).toBeNull()
  })

  it('switches between VLANs and prefixes', async () => {
    vi.stubGlobal('fetch', api().fn)
    const onSub = vi.fn()
    renderWithApp(<IpamView types={types} sub="vlans" onSub={onSub} canEdit sourceName={names} />)
    fireEvent.click(await screen.findByText('Prefixes 2'))
    expect(onSub).toHaveBeenCalledWith('prefixes')
  })
})

describe('ipNum', () => {
  it('sorts addresses by number, ranges by their start', () => {
    expect(ipNum('192.0.2.0/24')).toBeLessThan(ipNum('192.0.10.0/24'))
    expect(ipNum('192.0.2.128-192.0.2.200')).toBeGreaterThan(ipNum('192.0.2.0/25'))
    expect(ipNum('nope')).toBe(Number.MAX_SAFE_INTEGER)
  })
})
