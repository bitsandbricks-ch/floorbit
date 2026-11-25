import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DeviceEndpoints } from './DeviceEndpoints'
import { DeviceNetworks } from './DeviceNetworks'

afterEach(() => vi.unstubAllGlobals())

describe('Device: Networks and VLANs, MAC and IP (issue #903)', () => {
  it('lists the VLANs with their networks, and the networks with their VLAN', () => {
    renderWithApp(<DeviceNetworks found={{
      vlans: [{ id: 100, name: 'players' }, { id: 10, name: 'mgmt' }],
      networks: ['192.0.2.0/25'],
      svis: [{ vlan: 100, network: '198.51.100.0/24' }],
      routes: [], at: '2026-11-24T20:00:00Z',
    }} />)
    const vlans = screen.getByRole('table', { name: 'VLANs on the device' })
    const rows = within(vlans).getAllByRole('row').slice(1)
    expect(rows.map((r) => r.textContent)).toEqual(['10mgmt–', '100players198.51.100.0/24'])
    const nets = screen.getByRole('table', { name: 'Networks on the device' })
    expect(within(nets).getByText('100 · players')).toBeInTheDocument()
    expect(within(nets).getByText('192.0.2.0/25')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Routes on the device' })).toBeNull()
  })

  it('says how to get them when nothing was discovered', () => {
    renderWithApp(<DeviceNetworks found={undefined} />)
    expect(screen.getByText('Nothing discovered yet')).toBeInTheDocument()
  })

  it('shows the machines seen on the device\'s ports', async () => {
    const now = Date.now() / 1000
    const api = fakeFetch({ 'GET /api/endpoints?device=sw-a-01': {
      rows: [{ mac: '02:00:00:00:00:01', ip: '192.0.2.17', device: 'sw-a-01', port: 'Gi1/0/2', seat: 'A-2', vlan: 100, first_seen: now - 600, last_seen: now }],
      status: { store: 'database', written: 1, open: 0, keep_days: 7, error: null },
    } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<DeviceEndpoints name="sw-a-01" />)
    const table = await screen.findByRole('table', { name: 'Machines seen on sw-a-01' })
    expect(within(table).getByText('192.0.2.17')).toBeInTheDocument()
    expect(within(table).getByRole('link', { name: 'A-2' })).toHaveAttribute('href', '/endpoints?seat=A-2')
  })
})
