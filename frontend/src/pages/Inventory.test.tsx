import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device, DeviceDetail, InventoryList, InventoryOverview } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Route, Routes } from 'react-router-dom'
import Inventory from './Inventory'
import DevicePage from './inventory/DevicePage'
import EntryPage from './inventory/EntryPage'
import ScopePage from './inventory/ScopePage'
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
  location: '',
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
  drift: [],
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

/** The inventory with its item pages, so a click on a name opens the device's page. */
function app(route = '/inventory') {
  return renderWithApp(
    <Routes>
      <Route path="/inventory" element={<Inventory />} />
      <Route path="/inventory/devices/:id" element={<DevicePage />} />
      <Route path="/inventory/groups/:id" element={<ScopePage kind="group" />} />
      <Route path="/inventory/entries/:type/:id" element={<EntryPage />} />
    </Routes>, route)
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
    app()
    const row = (await screen.findByRole('link', { name: 'Stage switch' })).closest('tr')!
    expect(within(row).getByText('NetBox')).toBeInTheDocument()
    expect(within(row).getByLabelText('Name')).toBeInTheDocument()   // the lock icon
    const handRow = screen.getByRole('link', { name: 'sw-hand' }).closest('tr')!
    expect(within(handRow).getByText('By hand')).toBeInTheDocument()
    expect(screen.getByText('2 devices')).toBeInTheDocument()
  })

  it('counts what differs from the device per row and shows it all as one diff (#903)', async () => {
    const drifting = { ...list, devices: [{ ...list.devices[0], drift: 2 }, hand] }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': drifting, 'GET /api/inventory/groups': overview,
      'GET /api/inventory/drift': { devices: [{ id: 'netbox-12', name: 'Stage switch', drift: [
        { kind: 'field', field: 'model', configured: 'C9200', actual: 'C9300-48P' },
        { kind: 'address', field: 'mgmt_ip', configured: '192.0.2.5', actual: '192.0.2.6' },
      ] }] },
    }).fn)
    app()
    const row = (await screen.findByRole('link', { name: 'Stage switch' })).closest('tr')!
    expect(within(row).getByText('2 differences')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Differs from the device 1' }))
    expect(await screen.findByRole('group', { name: 'Management address' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it("shows each device's uplink, its last 24 hours and who reads it (#981)", async () => {
    const day = Array.from({ length: 24 }, (_, i) => (i === 20 ? 2400 : 0))
    const cols = { ...list, devices: [
      { ...list.devices[0], agent: 'a1', last_day: day,
        uplink: { port: 'Gi1/0/48', peer: 'dist-01', peer_port: 'Te1/1/1', speed_bps: 1e9, planned_gbps: 10, state: 'up', issue: 'slow' } },
      { ...hand, agent: '' },
    ] }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': cols, 'GET /api/inventory/groups': overview,
      'GET /api/options/agents': { options: [{ value: 'a1', label: 'Hall agent' }] },
    }).fn)
    app()
    const row = (await screen.findByRole('link', { name: 'Stage switch' })).closest('tr')!
    expect(within(row).getByText('1G of 10G')).toBeInTheDocument()
    expect(within(row).getByLabelText('1 hour with an outage in the last 24 hours')).toBeInTheDocument()
    expect(await within(row).findByText('Hall agent')).toBeInTheDocument()
    const handRow = screen.getByRole('link', { name: 'sw-hand' }).closest('tr')!
    expect(within(handRow).getByText('Auto')).toBeInTheDocument()
  })

  it('picks devices and tags, groups or hides them in one request (#980)', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'POST /api/inventory/bulk': { changed: ['netbox-12', 'h1'], unchanged: 0 },
    })
    vi.stubGlobal('fetch', api.fn)
    app()
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Pick Stage switch' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Pick sw-hand' }))
    const bar = screen.getByRole('toolbar', { name: 'Act on the picked devices' })
    expect(within(bar).getByText('2 devices picked')).toBeInTheDocument()
    // Without ports.act there is no console to open.
    expect(within(bar).queryByRole('button', { name: 'Run command' })).toBeNull()
    fireEvent.click(within(bar).getByRole('button', { name: 'Add tag' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'core' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/inventory/bulk')?.body)
      .toEqual({ ids: ['netbox-12', 'h1'], action: 'tag-add', tag: 't1' }))
    expect(await screen.findByText('✓ Changed 2 devices')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'Clear the picks' }))
    expect(screen.queryByRole('toolbar', { name: 'Act on the picked devices' })).toBeNull()
  })

  it('shows no pick boxes to viewers', async () => {
    const viewer = { ...editor, user: { ...editor.user, role: 'viewer', permissions: ['floorplan.view'] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn)
    app()
    await screen.findByRole('link', { name: 'Stage switch' })
    expect(screen.queryByRole('checkbox', { name: 'Pick Stage switch' })).toBeNull()
  })

  it('says when the inventory syncs on its own', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory': { ...list, every: 15 }, 'GET /api/inventory/groups': overview }).fn)
    app()
    // The chip says the short version; its tooltip has the schedule.
    fireEvent.mouseEnter((await screen.findByText(/^NetBox (synced|not synced)/)).closest('[role=status]')!)
    expect(await screen.findByText(/Syncs on its own every 15 minutes\./)).toBeInTheDocument()
  })

  it('shows what NetBox says for a locked field and can take it back', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'PATCH /api/inventory/netbox-12': { ...fed, name: 'sw-a-01', locked: [] },
      'GET /api/inventory/netbox-12': fedDetail,
    })
    vi.stubGlobal('fetch', api.fn)
    app()
    fireEvent.click(await screen.findByRole('link', { name: 'Stage switch' }))
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
    app()
    fireEvent.click(await screen.findByRole('link', { name: 'sw-hand' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Edit details' }))
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()     // nothing changed yet
    fireEvent.change(await screen.findByLabelText('Model'), { target: { value: 'X1' } })
    // The shared save bar, as on every settings page (#993); Discard puts the old value back.
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect(screen.getByLabelText('Model')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'X1' } })
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
    app()
    fireEvent.click(await screen.findByRole('button', { name: 'More' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Icons' }))
    const dialog = await screen.findByRole('dialog', { name: 'Icon library' })
    expect(await within(dialog).findByText('No icons uploaded yet.')).toBeInTheDocument()
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>'
    const file = new File([svg], 'server_rack.svg', { type: 'image/svg+xml' })
    fireEvent.change(document.querySelector('input[type=file]')!, { target: { files: [file] } })
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'server rack', svg }))
    expect(await within(dialog).findByRole('img', { name: 'server rack' })).toBeInTheDocument()
  })

  it('lists entries of other types and saves their fields', async () => {
    const rackType = { id: 'rack', name: 'Rack or location', sort: 'stored', builtin: true, icon: '', default_icon: 'rack', color: '',
      fields: [{ key: 'height_u', label: 'Height (U)', kind: 'number', choices: [], default: '42', link: '' }], own_fields: [], properties: {}, features: {}, count: 1 }
    const deviceType = { ...rackType, id: 'device', name: 'Device', sort: 'device', fields: [], count: 2 }
    const rack = { id: 'r1', type: 'rack', name: 'R1', summary: '', detail: '', link: '', group_id: null, tags: [], properties: {}, icon: '', color: '', notes: '', fields: {} }
    const api = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'GET /api/inventory/types': { types: [deviceType, rackType], field_kinds: [] },
      'GET /api/inventory/entries?type=rack': { entries: [rack] },
      'GET /api/inventory/entries/rack/r1': { ...rack, resolved: { properties: {}, tags: [], look: { icon: { value: '', from: null }, color: { value: '', from: null } }, group_path: [] },
        field_values: [{ ...rackType.fields[0], value: '42', is_default: true }] },
      'PATCH /api/inventory/entries/rack/r1': { ...rack, fields: { height_u: '47' } },
    })
    vi.stubGlobal('fetch', api.fn)
    app()
    fireEvent.click(await screen.findByRole('tab', { name: /Rack or location/ }))
    expect(await screen.findByText('42')).toBeInTheDocument()     // the default shows in the list
    fireEvent.click(screen.getByRole('button', { name: 'R1' }))
    const height = await screen.findByLabelText('Height (U)')
    expect(height).toHaveAttribute('placeholder', '42')
    fireEvent.change(height, { target: { value: '47' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[0])
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ fields: { height_u: '47' } }))
  })

  it('leaves cables and power to their own tabs: one row of type tabs (#1426)', async () => {
    const deviceType = { id: 'device', name: 'Device', sort: 'device', builtin: true, icon: '', default_icon: 'other', color: '',
      fields: [], own_fields: [], properties: {}, features: {}, count: 2 }
    const linked = (id: string, name: string) => ({ ...deviceType, id, name, sort: 'linked', count: 3 })
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'GET /api/inventory/types': { types: [deviceType, linked('cable', 'Cable'), linked('circuit', 'Circuit'),
        linked('power-board', 'Power board'), linked('patch-panel', 'Patch panel')], field_kinds: [] },
    }).fn)
    app()
    expect(await screen.findByRole('tab', { name: /Patch panel/ })).toBeInTheDocument()
    for (const name of [/^Cable/, /^Circuit/, /^Power board/]) expect(screen.queryByRole('tab', { name })).toBeNull()
  })

  it('shows viewers the list without edit buttons', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({ 'GET /api/auth/me': { enabled: true, user: { ...editor.user, role: 'viewer', permissions: ['floorplan.view'] } }, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn,
    )
    app()
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
    app()
    fireEvent.click(await screen.findByRole('button', { name: 'Sync now' }))
    expect(await screen.findByText('✓ Synced: 2 added, 1 updated, 0 gone, 1 edited fields kept.')).toBeInTheDocument()
  })

  it('filters by group (with the groups below it) and by tag', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview }).fn)
    app()
    await screen.findByRole('link', { name: 'sw-hand' })
    // Picking a group or a tag on the Groups and tags tab goes back to the list, filtered.
    fireEvent.click(screen.getByRole('tab', { name: 'Groups and tags' }))
    fireEvent.click(await screen.findByRole('button', { name: /^Hall A/ }))
    await waitFor(() => expect(screen.queryByRole('link', { name: 'sw-hand' })).toBeNull())
    expect(screen.getByRole('link', { name: 'Stage switch' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Groups and tags' }))
    fireEvent.click(await screen.findByRole('button', { name: /No group/ }))
    expect(await screen.findByRole('link', { name: 'sw-hand' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Stage switch' })).toBeNull()
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
    app()
    fireEvent.click(await screen.findByRole('link', { name: 'Stage switch' }))
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

  it('sets telemetry up on the Telemetry tab: automatic from its software, chosen ways, agent and ports over the group', async () => {
    const hallA = { type: 'group' as const, id: 'g1', name: 'Hall A' }
    const detail: DeviceDetail = {
      ...fedDetail, blocks: [], properties: { 'telemetry.gnmi.port': '50052' },
      resolved: {
        ...fedDetail.resolved,
        properties: {
          'telemetry.snmp.port': { value: '1161', from: hallA },
          'telemetry.gnmi.port': { value: '50052', from: { type: 'device', id: 'netbox-12', name: 'Stage switch' } },
        },
        features: { ...fedDetail.resolved.features, telemetry: { on: true, from: hallA } },
      },
    }
    const info = {
      on: true, platform: 'nxos', logins: { snmp: 'snmp_v2c', trap: 'snmp_trap' },
      auto: { drivers: ['snmp', 'traps'], fdb: 'qbridge', vlans: [], mdt_node: 'Stage switch', address: '192.0.2.5' },
      target: { drivers: ['snmp', 'traps'], fdb: 'qbridge', vlans: [], mdt_node: null, address: '192.0.2.5', agent: '',
        trap_send_port: 1163, trap_user: 'trap-stage' },
    }
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list,
      'GET /api/inventory/groups': overview,
      'GET /api/inventory/netbox-12': detail,
      'GET /api/telemetry/devices/netbox-12': info,
      'GET /api/options/agents': { options: [{ value: 'a1', label: 'Rack A', hint: 'a1' }] },
      'PATCH /api/inventory/netbox-12': { ok: true },
    })
    vi.stubGlobal('fetch', api.fn)
    app()
    fireEvent.click(await screen.findByRole('link', { name: 'Stage switch' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'Telemetry' }))
    // On because its group says so; how follows from its software and logins.
    expect(await screen.findByText('Automatic for Cisco NX-OS (Nexus) with its logins: SNMP polling, SNMP traps.')).toBeInTheDocument()
    expect(screen.getByText(/^On ·/)).toHaveTextContent('from group Hall A')
    // Its own trap user has its own listener: where to send.
    expect(screen.getByText("Traps go to the agent's UDP port 1163, as the SNMPv3 user trap-stage. Each trap user has its own port.")).toBeInTheDocument()
    // Empty here: the group's port shows, and where it comes from.
    expect(screen.getByLabelText('SNMP port')).toHaveAttribute('placeholder', '1161')
    expect(screen.getByLabelText('gNMI port')).toHaveValue('50052')
    // Choosing starts from what it does now; MDT asks for its node name, the switch's own by default.
    expect(screen.queryByLabelText('MDT node name')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: 'Choose' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Cisco MDT dial-out' }))
    expect(screen.getByLabelText('MDT node name')).toHaveAttribute('placeholder', 'Stage switch')
    fireEvent.change(screen.getByLabelText('API port (NX-API, RESTCONF, OPNsense)'), { target: { value: '84x43' } })
    fireEvent.change(screen.getByLabelText('gNMI port'), { target: { value: '' } })
    // Collected by (issue #869): one agent, or the agents with a tag, with or without failover.
    fireEvent.click(screen.getByRole('combobox', { name: 'Collected by' }))
    expect(await screen.findByRole('option', { name: /Rack A/, hidden: true })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'Agents tagged core', hidden: true }))
    fireEvent.click(screen.getByRole('combobox', { name: 'While it is away' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Nobody collects (no failover)', hidden: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      properties: { 'telemetry.agent': 'tag:t1', 'telemetry.failover': 'false', 'telemetry.api.port': '8443',
        'telemetry.drivers': 'snmp traps mdt' },
      features: { ...detail.features, telemetry: null },
    }))
  })

  it('turns telemetry off for one device', async () => {
    const detail: DeviceDetail = {
      ...fedDetail, blocks: [],
      resolved: { ...fedDetail.resolved, features: { ...fedDetail.resolved.features, telemetry: { on: true, from: { type: 'defaults', id: 'defaults', name: '' } } } },
    }
    const api = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'GET /api/inventory/netbox-12': detail, 'PATCH /api/inventory/netbox-12': { ok: true },
      'GET /api/telemetry/devices/netbox-12': { on: true, platform: 'ios', logins: {}, auto: { drivers: [], fdb: 'cisco_vlans', vlans: [10], mdt_node: 'x', address: 'x' }, target: null },
    })
    vi.stubGlobal('fetch', api.fn)
    app('/inventory/devices/netbox-12?tab=telemetry')
    await waitFor(() => expect(screen.getByRole('radio', { name: 'Off' })).toBeEnabled())     // once it knows who may edit
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()     // nothing changed yet
    fireEvent.click(screen.getByRole('radio', { name: 'Off' }))
    // Off: nothing left to set up.
    expect(screen.queryByLabelText('MAC tables')).toBeNull()
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      properties: detail.properties ?? {}, features: { ...detail.features, telemetry: false },
    }))
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
    app()
    fireEvent.click(await screen.findByRole('link', { name: 'Stage switch' }))
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
    app()
    fireEvent.click(await screen.findByRole('tab', { name: 'Groups and tags' }))
    fireEvent.click(await screen.findByRole('button', { name: 'New group' }))
    // A new group opens on its own page.
    fireEvent.change((await screen.findAllByRole('textbox', { name: 'Name' }))[0], { target: { value: 'Core' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toMatchObject({ name: 'Core', parent_id: null, tags: [] }))
  })

  it("opens a device's own page from its address, with the plan and its group a click away", async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory': list, 'GET /api/inventory/groups': overview,
      'GET /api/inventory/netbox-12': { ...fedDetail, blocks: [] }, 'GET /api/inventory/credentials': { credentials: [] },
    }).fn)
    app('/inventory/devices/netbox-12')
    expect((await screen.findAllByRole('heading', { name: /Stage switch/ })).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'On the plan' })).toHaveAttribute('href', '/plan?switch=Stage%20switch')
    expect(screen.getByText('192.0.2.5', { selector: '.fb-chip-value' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()                    // a page, not a side panel
    fireEvent.click(screen.getByRole('link', { name: 'Hall A' }))
    expect((await screen.findAllByRole('textbox', { name: 'Name' }))[0]).toHaveValue('Hall A')
  })

  it('says so when a device is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory/groups': overview }).fn)
    app('/inventory/devices/nope')
    expect(await screen.findByText('This item is not in the inventory')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the inventory' })).toHaveAttribute('href', '/inventory')
  })
})
