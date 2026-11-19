import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Telemetry from './Telemetry'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['settings.manage'] } }
const core = {
  id: 't1', name: 'core-01', address: '192.0.2.1', kind: 'switch', platform: 'nxos', drivers: ['snmp', 'nxapi'],
  snmp_version: '2c', auth_protocol: '', priv_protocol: '', fdb: 'qbridge', vlans: [], port: null, verify_tls: true,
  tables: true, mdt_node: null, url: null, username: 'ro', secrets: ['community', 'password'],
}
const settings = {
  targets: [core], seen: { 'core-01': { seen: 1_763_100_000, online: true, ports: 52, macs: 0, arp: 812, neighbours: 4 } },
  status: { collector: 'agent', devices: 1, points: 1234, unknown: 0, poll_errors: { 'core-01': 'NX-API on core-01 refused the login.' },
    storage: { mode: 'lite', logs: null, keep_days: 2, errors: {} } },
  drivers: ['snmp', 'traps', 'gnmi', 'mdt', 'nxapi', 'restconf', 'opnsense', 'push'],
  platforms: ['nxos', 'iosxe', 'ios', 'opnsense', 'pfsense', 'other'], kinds: ['switch', 'router', 'firewall'],
  fdb_modes: ['qbridge', 'cisco_vlans', 'bridge', 'off'],
}

describe('Telemetry', () => {
  it('lists devices with what came in and their errors, never their secrets', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/settings/telemetry': settings,
      'GET /api/options/switches': { options: [{ value: 'core-01', label: 'core-01' }] },
      'GET /api/settings/telemetry/targets/t1/device-config': { config: 'feature nxapi' },
      'GET /api/settings/telemetry/token': { token: 'fbt_example' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Telemetry />)
    expect(await screen.findByText('core-01')).toBeInTheDocument()
    expect(screen.getByText('52 ports, 0 MACs, 812 ARP, 4 neighbours')).toBeInTheDocument()
    expect(screen.getByText('NX-API on core-01 refused the login.')).toBeInTheDocument()
    expect(screen.getByText("Floorbit's database, 2 days")).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Device setup' }))
    expect(await screen.findByText('feature nxapi')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show the token' }))
    expect(await screen.findByText('fbt_example')).toBeInTheDocument()
  })

  it('says why a device sends nothing, in words', async () => {
    const problem = { driver: 'snmp', kind: 'refused', address: '192.0.2.1:161', since: 1_763_100_000, at: 1_763_100_060, count: 3,
      detail: 'agent udp://192.0.2.1:161: performing get on field sysName: recvfrom: connection refused' }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/options/switches': { options: [] },
      'GET /api/settings/telemetry': { ...settings, seen: { 'core-01': { seen: null, online: false, problems: [problem] } } },
    }).fn)
    renderWithApp(<Telemetry />)
    expect(await screen.findByText(/SNMP polling: nothing listens on 192.0.2.1:161/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'What to check' })).toHaveAttribute('href', expect.stringContaining('#when-a-device-sends-nothing'))
  })

  it('keeps a stored secret when the field is left empty', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/settings/telemetry': settings,
      'GET /api/options/switches': { options: [{ value: 'core-01', label: 'core-01' }] },
      'PUT /api/settings/telemetry/targets/t1': core,
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Telemetry />)
    fireEvent.click(await screen.findByRole('button', { name: 'Change' }))
    expect(screen.getAllByPlaceholderText('Set. Leave empty to keep it.').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')).toBeTruthy())
    const sent = api.calls.find((c) => c.method === 'PUT')!.body as Record<string, unknown>
    expect(sent.name).toBe('core-01')
    expect('community' in sent || 'password' in sent).toBe(false)
  })
})
