import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Switches from './Switches'
import { switchRows } from './switches/rows'

afterEach(() => vi.unstubAllGlobals())

const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const base = {
  x: null, y: null, placed: false, origin: 'manual', hidden: false, updated_at: '', sources: [], locked: [], gone: [], fed: {},
  model: '', serial: '', mgmt_ip: '', hall: 'Hall A', status: 'active', notes: '', platform: '', os: '', cpu: '', cores: '',
  memory_mb: '', disk_gb: '', host: '', location: '', icon: '', color: '', group_id: null, tags: [], properties: {}, features: {},
} as unknown as Device
const up = (peer: string, load: number | null, issue: '' | 'slow' = '') => ({
  port: 'Te1/1/1', peer, peer_port: 'Te1/0/1', speed_bps: 10e9, planned_gbps: 10, state: 'up' as const, issue, load,
})
const devices: Device[] = [
  { ...base, id: 'c', name: 'core-01', role: 'switch', state: 'online', ports: { up: 46, total: 48 }, uplink: null, seats: 0, last_day: Array(24).fill(0) },
  { ...base, id: 'd', name: 'dist-01', role: 'switch', state: 'online', ports: { up: 22, total: 24 }, uplink: up('core-01', 0.84), seats: 0 },
  { ...base, id: 'a', name: 'sw-a-01', role: 'switch', state: 'online', ports: { up: 45, total: 48 }, uplink: up('dist-01', 0.22), seats: 44,
    poe: { budget_w: 740, used_w: 210 } },
  { ...base, id: 'b', name: 'sw-b-03', role: 'switch', state: 'offline', ports: { up: 0, total: 48 }, uplink: up('dist-01', null), seats: 24 },
  { ...base, id: 'f', name: 'fw-01', role: 'firewall', state: 'online' },
] as Device[]
const list = { devices, sources: [], every: 15, roles: ['switch', 'firewall'], fields: [] }

describe('switchRows', () => {
  it('works the tier out of the topology, not a field', () => {
    const tiers = Object.fromEntries(switchRows(devices).map((r) => [r.d.name, r.tier]))
    expect(tiers).toEqual({ 'core-01': 'core', 'dist-01': 'distribution', 'sw-a-01': 'access', 'sw-b-03': 'access' })
  })
})

describe('Switches (#902)', () => {
  it('lists the switches with live columns and sums them up in four figures', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/inventory': list }).fn)
    renderWithApp(<Switches />)
    const table = await screen.findByRole('table', { name: 'Switches' })
    expect(within(table).queryByText('fw-01')).not.toBeInTheDocument()
    const row = within(table).getByRole('link', { name: 'sw-a-01' }).closest('tr')!
    expect(within(row).getByText('44')).toBeInTheDocument()
    expect(within(row).getByText('45 / 48')).toBeInTheDocument()
    expect(within(row).getByText('210 / 740 W')).toBeInTheDocument()
    expect(within(row).getByRole('meter', { name: 'Uplink load' })).toHaveAttribute('aria-valuenow', '22')
    expect(within(table).getByRole('link', { name: 'sw-a-01' })).toHaveAttribute('href', '/inventory/devices/a')
    expect(screen.getByText('3 / 4')).toBeInTheDocument()
    expect(screen.getByText('sw-b-03 down: 24 seats offline')).toBeInTheDocument()
    expect(screen.getByText('84 %')).toBeInTheDocument()
    expect(screen.getByText('dist-01 → core-01')).toBeInTheDocument()
    expect(screen.getByText('210 W')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open in Inventory' })).toHaveAttribute('href', '/inventory?role=switch')
  })
})
