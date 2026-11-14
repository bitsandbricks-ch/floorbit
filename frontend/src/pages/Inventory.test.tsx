import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Device, InventoryList } from '@/api/types'
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
  roles: ['switch', 'router', 'firewall', 'access-point', 'server', 'other'],
  fields: ['name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes'],
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
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory': list }).fn)
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
      'GET /api/inventory': list,
      'PATCH /api/inventory/netbox-12': { ...fed, name: 'sw-a-01', locked: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stage switch' }))
    expect(await screen.findByText('Changed by hand. NetBox says: sw-a-01')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "Use NetBox's value" }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ unlock: ['name'] }))
  })

  it('sends only the fields that changed', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor,
      'GET /api/inventory': list,
      'PATCH /api/inventory/h1': { ...hand, model: 'X1' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'sw-hand' }))
    fireEvent.change(await screen.findByLabelText('Model'), { target: { value: 'X1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ model: 'X1' }))
  })

  it('shows viewers the list without edit buttons', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({ 'GET /api/auth/me': { enabled: true, user: { ...editor.user, role: 'viewer', permissions: ['floorplan.view'] } }, 'GET /api/inventory': list }).fn,
    )
    renderWithApp(<Inventory />)
    expect(await screen.findByText('Stage switch')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add device' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Stage switch' })).toBeNull()
  })

  it('reports a sync', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({
        'GET /api/auth/me': editor,
        'GET /api/inventory': list,
        'POST /api/inventory/sync': { reports: [{ plugin: 'netbox', at: 'x', added: 2, updated: 1, gone: 0, locked: 1 }] },
      }).fn,
    )
    renderWithApp(<Inventory />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sync now' }))
    expect(await screen.findByText('✓ Synced: 2 added, 1 updated, 0 gone, 1 edited fields kept.')).toBeInTheDocument()
  })
})
