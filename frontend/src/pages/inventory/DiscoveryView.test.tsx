import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { FoundList } from '@/api/inventoryFound'
import { DiscoveryView } from './DiscoveryView'

afterEach(() => vi.unstubAllGlobals())

const editor = { enabled: true, user: { username: 'ed', display_name: 'Ed', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const now = Date.now() / 1000
const found: FoundList = {
  devices: [{ name: 'sw-c-02.example.com', protocol: 'lldp', seen_by: [{ switch: 'dist-02', port: 'Te1/1/4', remote_port: 'Te1/1/1' }] }],
  links: [{ key: 'core-01|eth1/12 -- fw-01|ix2', a: 'core-01', a_port: 'Eth1/12', b: 'fw-01', b_port: 'ix2', protocol: 'lldp', speed: 10 }],
  ignored: { devices: 0, links: 0 },
}
const senders = [{ address: '192.0.2.200', name: '', kinds: { syslog: 4 }, first: now - 600, last: now - 60, agents: ['Agent A'], ignored: false }]

describe('Inventory › Discovery (#891)', () => {
  it('lists found devices and links, adds one prefilled, confirms a link and ignores', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory/found': found, 'GET /api/inventory/unknown-senders': { senders },
      'POST /api/links': () => ({ status: 201, body: {} }), 'POST /api/inventory/found/ignore': { ok: true },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Routes>
      <Route path="/inventory" element={<DiscoveryView canEdit />} />
      <Route path="/inventory/devices/new" element={<p>new device page</p>} />
    </Routes>, '/inventory')
    const devices = await screen.findByRole('table', { name: 'Devices' })
    expect(await within(devices).findByText('unknown: sends syslog')).toBeInTheDocument()
    const row = within(devices).getByText('sw-c-02.example.com (LLDP)').closest('tr')!
    expect(within(row).getByText('LLDP on dist-02 Te1/1/4')).toBeInTheDocument()
    const links = screen.getByRole('table', { name: 'Links' })
    fireEvent.click(within(links).getByRole('button', { name: 'Confirm link' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/links')?.body)
      .toEqual({ a: 'core-01', a_port: 'Eth1/12', b: 'fw-01', b_port: 'ix2', speed: 10 }))
    fireEvent.click(within(links).getByRole('button', { name: 'Ignore' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/inventory/found/ignore')?.body)
      .toEqual({ kind: 'link', key: 'core-01|eth1/12 -- fw-01|ix2' }))
    fireEvent.click(within(row).getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('new device page')).toBeInTheDocument()
  })
})
