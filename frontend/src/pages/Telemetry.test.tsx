import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Telemetry from './Telemetry'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['settings.manage'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const core = {
  id: 'inv-d1', name: 'core-01', address: '192.0.2.1', kind: 'router', platform: 'nxos', drivers: ['snmp', 'nxapi'],
  agent: 'a1', inventory_id: 'd1', ports: {},
}
const fw = { id: 'inv-d2', name: 'fw-01', address: '192.0.2.41', kind: 'firewall', platform: 'opnsense', drivers: ['push'], agent: '', inventory_id: 'd2', ports: {} }
const overview = {
  devices: [core, fw], seen: { 'core-01': { seen: 1_763_100_000, online: true, ports: 52, macs: 0, arp: 812, neighbours: 4 } },
  status: { collector: 'agent', devices: 1, points: 1234, unknown: 0, poll_errors: { 'core-01': 'NX-API on core-01 refused the login.' },
    storage: { mode: 'lite', logs: null, keep_days: 2, errors: {} } },
}
const agents = { options: [{ value: 'a1', label: 'Hall A agent', hint: 'a1' }] }

describe('Telemetry', () => {
  it('lists the inventory devices with what came in, their agent and errors', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/telemetry/overview': overview, 'GET /api/options/agents': agents,
      'GET /api/telemetry/token': { token: 'fbt_example' },
    }).fn)
    renderWithApp(<Telemetry />)
    // Each device opens its own page, on the Telemetry tab, where it is set up and tested.
    expect(await screen.findByRole('link', { name: 'core-01' })).toHaveAttribute('href', '/inventory/devices/d1?tab=telemetry')
    expect(screen.getByRole('link', { name: /: fw-01$/ })).toHaveAttribute('href', '/inventory/devices/d2?tab=telemetry')
    expect(screen.getByText('52 ports, 0 MACs, 812 ARP, 4 neighbours')).toBeInTheDocument()
    expect(await screen.findByText('Hall A agent')).toBeInTheDocument()
    expect(screen.getByText('Any agent')).toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()       // heard from
    expect(screen.getByRole('link', { name: 'Open the inventory' })).toHaveAttribute('href', '/inventory')
    // Devices are set up in the inventory: nothing here adds or changes one.
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    // Find and filter.
    fireEvent.change(screen.getByRole('textbox', { name: 'Find a device' }), { target: { value: 'opn' } })
    expect(screen.queryByRole('link', { name: 'core-01' })).toBeNull()
    expect(screen.getByRole('link', { name: 'fw-01' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Find a device' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Never heard' }))
    expect(screen.queryByRole('link', { name: 'core-01' })).toBeNull()
    // The collector's own state and its errors have their tab; the token its own.
    fireEvent.click(screen.getByRole('tab', { name: /Collector/ }))
    expect(screen.getByText('NX-API on core-01 refused the login.')).toBeInTheDocument()
    expect(screen.getAllByText("Floorbit's database, 2 days")).toHaveLength(2)     // the summary card and the tab
    fireEvent.click(screen.getByRole('tab', { name: 'Senders' }))
    fireEvent.click(screen.getByRole('button', { name: 'Show the token' }))
    expect(await screen.findByText('fbt_example')).toBeInTheDocument()
  })

  it('shows the crew the devices without the admin tools', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/telemetry/overview': overview, 'GET /api/options/agents': agents }).fn)
    renderWithApp(<Telemetry />)
    expect((await screen.findAllByText('core-01')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Test now' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Senders' })).toBeNull()
  })

  it('says how to add devices when there are none', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/telemetry/overview': { ...overview, devices: [], seen: {} }, 'GET /api/options/agents': agents }).fn)
    renderWithApp(<Telemetry />)
    expect(await screen.findByText(/Turn on Telemetry for the core/)).toBeInTheDocument()
  })

  it('says why a device sends nothing, in words', async () => {
    const problem = { driver: 'snmp', kind: 'refused', address: '192.0.2.1:161', since: 1_763_100_000, at: 1_763_100_060, count: 3,
      detail: 'agent udp://192.0.2.1:161: performing get on field sysName: recvfrom: connection refused' }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/options/agents': agents,
      'GET /api/telemetry/overview': { ...overview, seen: { 'core-01': { seen: null, online: false, problems: [problem] } } },
    }).fn)
    renderWithApp(<Telemetry />)
    expect(await screen.findByText(/SNMP polling: nothing listens on 192.0.2.1:161/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'What to check' })).toHaveAttribute('href', expect.stringContaining('#when-a-device-sends-nothing'))
  })
})
