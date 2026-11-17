import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device, DeviceDetail, InventoryList, InventoryOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Inventory from './Inventory'
import { matches } from './inventory/model'

afterEach(() => vi.unstubAllGlobals())

const fed: Device = {
  id: 'netbox-12',
  name: 'Stage switch',
  role: 'switch',
  model: 'C9200',
  serial: 'FOC123',
  mgmt_ip: '192.0.2.5',
  hall: 'Hall A',
  status: 'active',
  notes: '',
  platform: '',
  os: '',
  cpu: '',
  cores: '',
  memory_mb: '',
  disk_gb: '',
  host: '',
  x: 10,
  y: 20,
  placed: true,
  origin: 'netbox',
  hidden: false,
  updated_at: '2026-11-14T02:00:00Z',
  sources: ['netbox'],
  locked: ['name'],
  gone: [],
  fed: { netbox: { name: 'sw-a-01', model: 'C9200' } },
}
const hand: Device = { ...fed, id: 'h1', name: 'sw-hand', model: '', origin: 'manual', sources: [], locked: [], fed: {}, placed: false }

const list: InventoryList = {
  devices: [fed, hand],
  sources: [{ id: 'netbox', name: 'NetBox', last_sync: { plugin: 'netbox', at: '2026-11-14T02:00:00Z', added: 1 } }],
  roles: ['switch', 'router', 'firewall', 'access-point', 'server', 'vm', 'pdu', 'other'],
  fields: ['name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes'],
}
list.devices[0] = { ...fed, group_id: 'g1', interface_count: 1, blocked: 1 }
const overview: InventoryOverview = {
  groups: [
    { id: 'g1', name: 'Hall A', parent_id: null, icon: 'switch', color: '#1e88e5', tags: [], notes: '', properties: { site: 'hall-a' }, features: {}, devices: 1, credentials: ['ssh'] },
    { id: 'g2', name: 'Row 1', parent_id: 'g1', icon: '', color: '', tags: ['t1'], notes: '', properties: {}, features: {}, devices: 0, credentials: [] },
  ],
  tags: [{ id: 't1', name: 'core', icon: '', color: '#e53935', description: '', properties: {}, features: {}, used: 1, credentials: [] }],
  defaults: { properties: {}, features: {}, credentials: [] },
  features: [
    { id: 'ports', core: true, name: 'ports', default: true },
    { id: 'ssh-ports', core: false, name: 'SSH port actions', default: false, agent: true },
  ],
  icons: ['switch', 'server', 'vm', 'other'],
  credential_kinds: ['ssh', 'snmp_v2c', 'snmp_v3', 'api', 'http'],
  auth_protocols: ['SHA'],
  priv_protocols: ['AES'],
  ungrouped: 1,
}
const fedDetail: DeviceDetail = {
  ...fed,
  group_id: 'g1',
  interfaces: [
    { id: 'i1', name: 'Gi1/0/1', type: 'copper', speed_mbps: 1000, mac: '', ips: [], vlan: 10, mode: 'access', description: 'Seat A-1', enabled: true, mgmt: false, lag: '', origin: 'netbox', hidden: false, sources: ['netbox'], locked: [], gone: [], fed: {} },
  ],
  own_credentials: [],
  blocks: [{ credential_id: 'c1', rev: 'r1', kind: 'ssh', plugin: 'ssh-ports', message: 'Authentication failed', agent: 'Hall agent', at: 1763380000, device_id: 'netbox-12', device: 'Stage switch' }],
  resolved: {
    properties: { site: { value: 'hall-a', from: { type: 'group', id: 'g1', name: 'Hall A' } } },
    features: { ports: { on: true, from: null }, 'ssh-ports': { on: true, from: { type: 'group', id: 'g1', name: 'Hall A' } } },
    tags: [],
    look: { icon: { value: 'switch', from: { type: 'group', id: 'g1', name: 'Hall A' } }, color: { value: '#1e88e5', from: { type: 'group', id: 'g1', name: 'Hall A' } } },
    credentials: { ssh: { id: 'c1', kind: 'ssh', owner_type: 'group', owner_id: 'g1', username: 'ops', auth_protocol: '', priv_protocol: '', rev: 'r1', set_at: 1, set_by: 'admin', secrets: ['secret'], from: { type: 'group', id: 'g1', name: 'Hall A' }, blocked: true } },
    group_path: [{ id: 'g1', name: 'Hall A' }],
  },
}
const editor = {
  enabled: true,
  user: { username: 'ed', display_name: 'Ed', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] },
}

describe('matches', () => {
  it('searches name, model, serial and IP, and filters by role', () => {
    expect(matches(fed, 'foc1', null)).toBe(true)
    expect(matches(fed, '192.0.2', null)).toBe(true)
    expect(matches(fed, 'nothing', null)).toBe(false)
    expect(matches(fed, '', 'router')).toBe(false)
  })
})

describe('Inventory page', () => {
  it('lists devices with where they come from and what was changed by hand', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn)
    renderWithApp(<Inventory />)
    const row = (await screen.findByRole('button', { name: 'Stage switch' })).closest('tr')!
    expect(within(row).getByText('NetBox')).toBeInTheDocument()
    expect(within(row).getByLabelText('Name')).toBeInTheDocument()   // the lock icon
    const handRow = screen.getByRole('button', { name: 'sw-hand' }).closest('tr')!
    expect(within(handRow).getByText('By hand')).toBeInTheDocument()
    expect(screen.getByText('2 devices')).toBeInTheDocument()
  })

  it('shows what NetBox says for a locked field and can take it back', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'PATCH /api/inventory/netbox-12': { ...fed, name: 'sw-a-01', locked: [] },
      'GET /api/inventory/netbox-12': fedDetail,
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stage switch' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    expect(await screen.findByText('Changed by hand. NetBox says: sw-a-01')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "Use NetBox's value" }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ unlock: ['name'] }))
  })

  it('sends only the fields that changed', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'PATCH /api/inventory/h1': { ...hand, model: 'X1' },
      'GET /api/inventory/h1': { ...fedDetail, ...hand, blocks: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'sw-hand' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    fireEvent.change(await screen.findByLabelText('Model'), { target: { value: 'X1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ model: 'X1' }))
  })

  it('lets admins upload SVG icons to the shared library', async () => {
    const admin = { ...editor, user: { ...editor.user, permissions: [...editor.user.permissions, 'settings.manage'] } }
    const rack = { id: 'custom-0123456789ab', name: 'server rack', url: '/api/icons/custom-0123456789ab.svg', by: 'ed', at: 1 }
    let uploaded = false
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'GET /api/icons': () => ({ body: { icons: uploaded ? [rack] : [], max_kb: 64 } }),
      'POST /api/icons': () => { uploaded = true; return { status: 201, body: rack } },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Icons' }))
    const dialog = await screen.findByRole('dialog', { name: 'Icon library' })
    expect(await within(dialog).findByText('No icons uploaded yet.')).toBeInTheDocument()
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>'
    const file = new File([svg], 'server_rack.svg', { type: 'image/svg+xml' })
    fireEvent.change(document.querySelector('input[type=file]')!, { target: { files: [file] } })
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'server rack', svg }))
    expect(await within(dialog).findByRole('img', { name: 'server rack' })).toBeInTheDocument()
  })

  it('shows viewers the list without edit buttons', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({ 'GET /api/auth/me': { enabled: true, user: { ...editor.user, role: 'viewer', permissions: ['floorplan.view'] } }, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn,
    )
    renderWithApp(<Inventory />)
    expect(await screen.findByText('Stage switch')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add device' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New group' })).toBeNull()
  })

  it('reports a sync', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({
        'GET /api/auth/me': editor,
        'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
        'POST /api/inventory/sync': { reports: [{ plugin: 'netbox', at: 'x', added: 2, updated: 1, gone: 0, locked: 1 }] },
      }).fn,
    )
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sync now' }))
    expect(await screen.findByText('✓ Synced: 2 added, 1 updated, 0 gone, 1 edited fields kept.')).toBeInTheDocument()
  })

  it('filters by group (with the groups below it) and by tag', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn)
    renderWithApp(<Inventory />)
    await screen.findByRole('button', { name: 'sw-hand' })
    fireEvent.click(await screen.findByRole('button', { name: /^Hall A/ }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'sw-hand' })).toBeNull())
    expect(screen.getByRole('button', { name: 'Stage switch' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /No group/ }))
    expect(await screen.findByRole('button', { name: 'sw-hand' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stage switch' })).toBeNull()
  })

  it('opens a device with its interfaces, where its settings come from, and a blocked login to clear', async () => {
    const tech = { enabled: true, user: { ...editor.user, permissions: ['floorplan.view', 'floorplan.edit', 'ports.act'] } }
    const api = fakeFetch({
      'GET /api/auth/me': tech,
      'GET /api/inventory': list,
      'GET /api/inventory/groups': overview,
      'GET /api/inventory/netbox-12': fedDetail,
      'POST /api/inventory/blocks/clear': { cleared: 1 },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stage switch' }))
    expect(await screen.findByText('Stored login blocked')).toBeInTheDocument()
    expect(screen.getByText('Authentication failed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/inventory/blocks/clear')?.body).toEqual({ device_id: 'netbox-12', credential_id: 'c1' }))
    fireEvent.click(screen.getByRole('tab', { name: /Interfaces/ }))
    expect(await screen.findByText('Gi1/0/1')).toBeInTheDocument()
    expect(screen.getByText('Seat A-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(await screen.findByText('hall-a')).toBeInTheDocument()
    expect(screen.getAllByText('from group Hall A').length).toBeGreaterThan(0)
  })

  it('adds interfaces by range', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list,
      'GET /api/inventory/groups': overview,
      'GET /api/inventory/netbox-12': { ...fedDetail, blocks: [] },
      'POST /api/inventory/netbox-12/interfaces': { added: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stage switch' }))
    fireEvent.click(await screen.findByRole('tab', { name: /Interfaces/ }))
    fireEvent.change(await screen.findByLabelText('Interfaces'), { target: { value: 'Gi1/0/1-48' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ names: 'Gi1/0/1-48' }))
  })

  it('makes a group from the tree', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list,
      'GET /api/inventory/groups': overview,
      'GET /api/inventory/credentials': { credentials: [] },
      'POST /api/inventory/groups': { ...overview.groups[1], id: 'g3', name: 'Core', parent_id: 'g1' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'New group' }))
    const panel = await screen.findByRole('dialog')
    fireEvent.change(within(panel).getAllByRole('textbox')[0], { target: { value: 'Core' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toMatchObject({ name: 'Core', parent_id: null, tags: [] }))
  })
})
