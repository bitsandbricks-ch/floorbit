import { fireEvent, screen, within } from '@testing-library/react'
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
  it('shows a square per device and method, and the collector at a glance (#904)', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/options/agents': agents, 'GET /api/telemetry/token': { token: 'fbt_example' },
      'GET /api/telemetry/overview': { ...overview, syslog: { 'core-01': 1_763_100_000 } },
    }).fn)
    renderWithApp(<Telemetry />)
    // fw-01 never reported: "with problems" (the default) lists it alone.
    expect(await screen.findByRole('link', { name: 'fw-01' })).toHaveAttribute('href', '/inventory/devices/d2?tab=telemetry')
    expect(screen.queryByRole('link', { name: 'core-01' })).toBeNull()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
    expect(screen.getByText('1 never heard, 0 late')).toBeInTheDocument()
    expect(screen.getByText('Storage accepts everything')).toBeInTheDocument()
    expect(screen.getByText('2 d')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Show/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /^All/, hidden: true }))
    const row = (await screen.findByRole('link', { name: 'core-01' })).closest('tr')!
    // SNMP and the API are set up and heard, syslog came in too; traps, gNMI and MDT aren't set up.
    expect(within(row).getByRole('img', { name: /^SNMP: heard/ })).toBeInTheDocument()
    expect(within(row).getByRole('img', { name: /^API: heard/ })).toBeInTheDocument()
    expect(within(row).getByRole('img', { name: /^Syslog: heard/ })).toBeInTheDocument()
    expect(within(row).getByRole('img', { name: 'Traps: not set up' })).toBeInTheDocument()
    expect(within(row).getByRole('cell', { name: 'Hall A agent' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the inventory' })).toHaveAttribute('href', '/inventory')
    // Find a device.
    fireEvent.change(screen.getByRole('textbox', { name: 'Find a device' }), { target: { value: 'opn' } })
    expect(screen.queryByRole('link', { name: 'core-01' })).toBeNull()
    // The collector's own state and its errors have their tab; the token its own.
    fireEvent.click(screen.getByRole('tab', { name: /Collector/ }))
    expect(screen.getByText('NX-API on core-01 refused the login.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Senders' }))
    fireEvent.click(screen.getByRole('button', { name: 'Show the token' }))
    expect(await screen.findByText('fbt_example')).toBeInTheDocument()
  })

  it('shows the crew the devices without the admin tools', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/telemetry/overview': overview, 'GET /api/options/agents': agents }).fn)
    renderWithApp(<Telemetry />)
    expect(await screen.findByRole('link', { name: 'fw-01' })).toBeInTheDocument()
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
    // The square says the kind; the last column the kind, where and since when, then the hint.
    expect(await screen.findByRole('img', { name: 'SNMP: Nothing listens' })).toBeInTheDocument()
    expect(screen.getByText('SNMP polling · whole device')).toBeInTheDocument()
    expect(screen.getByText('3 times')).toBeInTheDocument()
    expect(screen.getByText(/^Nothing listens on 192.0.2.1:161/)).toBeInTheDocument()
    expect(screen.queryByText(/recvfrom: connection refused/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: "Collector's line" }))
    expect(screen.getByText(/recvfrom: connection refused/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'What to check' })).toHaveAttribute('href', expect.stringContaining('#when-a-device-sends-nothing'))
  })

  it('lists a device that sends by itself without being in the inventory', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/options/agents': agents,
      'GET /api/telemetry/overview': { ...overview, seen: { ...overview.seen, 'fw-09': { seen: 1_763_100_000, online: true } } },
    }).fn)
    renderWithApp(<Telemetry />)
    fireEvent.click(await screen.findByRole('button', { name: /^Show/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /^All/, hidden: true }))
    expect(await screen.findByText('fw-09')).toBeInTheDocument()
    expect(screen.getByText('Sends by itself')).toBeInTheDocument()
  })
})
