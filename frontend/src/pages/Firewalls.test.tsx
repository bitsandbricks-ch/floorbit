import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FirewallList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Route, Routes } from 'react-router-dom'
import Firewalls from './Firewalls'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const list: FirewallList = {
  firewalls: [
    { id: 'f1', name: 'fw-01', model: 'Example FW', hall: '', status: 'online', serving: ['192.0.2.0/27', '192.0.2.32/27'], planned: ['192.0.2.0/27'], taken_over: ['192.0.2.32/27'], seats: 40 },
    { id: 'f2', name: 'fw-02', model: '', hall: '', status: 'offline', serving: [], planned: ['192.0.2.32/27'], taken_over: [], seats: 0 },
  ],
  ranges: [
    // One range over two firewalls: each half goes to its own, fw-02's half to the fallback.
    { id: 'r1', cidr: '192.0.2.0/26', name: 'Block A', firewalls: ['fw-01', 'fw-02'], fallback: ['fw-01'], state: 'failover', seats: 40,
      parts: [{ cidr: '192.0.2.0/27', firewall: 'fw-01', now: 'fw-01', state: 'primary', seats: 22 },
        { cidr: '192.0.2.32/27', firewall: 'fw-02', now: 'fw-01', state: 'failover', seats: 18 }] },
  ],
  counts: { firewalls: 2, down: 1, failover: 1, without: 0 }, unread: false,
}

describe('Firewalls', () => {
  it('shows each firewall and which ranges failed over, without edit buttons for viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/firewalls': list }).fn)
    renderWithApp(<Firewalls />)
    const down = await screen.findByRole('region', { name: 'fw-02' })
    expect(within(down).getByText('Down')).toBeInTheDocument()
    expect(within(down).getByText('Planned for 192.0.2.32/27')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'fw-01' })).getByText('Serves 2 ranges, 40 seats')).toBeInTheDocument()
    expect(screen.getByText('Block A (192.0.2.32/27) runs over fw-01, planned fw-02')).toBeInTheDocument()
    expect(screen.getByText('1 part of a range is not on its planned firewall')).toBeInTheDocument()
    expect(screen.getAllByText('then fw-01').length).toBeGreaterThan(0)
    expect(within(screen.getByRole('region', { name: 'fw-01' })).getByText('Took over 192.0.2.32/27')).toBeInTheDocument()
    expect(screen.queryByText(/Backup for/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add range' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change' })).not.toBeInTheDocument()
    // A range is an inventory item: its groups and tags live in the inventory's tab for ranges.
    expect(screen.getByRole('link', { name: 'The prefixes in the inventory' })).toHaveAttribute('href', '/inventory?type=prefix')
  })

  it('lets the crew add a range over several firewalls, in order, with a fallback', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': { ...list, ranges: [] },
      'POST /api/firewalls/ranges': () => ({ status: 201, body: list.ranges[0] }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Firewalls />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add range' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Range' }), { target: { value: '192.0.2.0-192.0.2.128' } })
    const input = (label: string) => screen.getAllByLabelText(label).filter((el) => el.tagName === 'INPUT' && el.getAttribute('type') !== 'hidden')[0]
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    // Both pickers keep their options in the page: pick from the one that was opened.
    const pick = async (label: string, name: string) => {
      const el = input(label)
      fireEvent.click(el)
      const list = await waitFor(() => document.getElementById(el.getAttribute('aria-controls') ?? '') as HTMLElement)
      fireEvent.click(within(list).getByRole('option', { name, hidden: true }))
    }
    await pick('Firewalls', 'fw-02')
    await pick('Firewalls', 'fw-01')
    expect(screen.getByText('Cut into 2 equal parts, one per firewall in this order.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      cidr: '192.0.2.0-192.0.2.128', name: '', firewalls: ['fw-02', 'fw-01'], fallback: [], switches: [],
    }))
  })

  it('names the switch groups of an imported range, and Switches opens its inventory page (#1062, #1312)', async () => {
    const imported = { ...list.ranges[0], source: 'import' as const, plugin: 'netbox', switches: ['g-green'] }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': { ...list, ranges: [imported] },
      'GET /api/inventory/groups': { groups: [{ id: 'g-green', name: 'Green' }], tags: [] },
    }).fn)
    renderWithApp(
      <Routes>
        <Route path="/" element={<Firewalls />} />
        <Route path="/inventory/entries/prefix/:id" element={<p>Range page {imported.id}</p>} />
      </Routes>,
    )
    expect(await screen.findByText('For: Green')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Switches' }))
    expect(await screen.findByText(`Range page ${imported.id}`)).toBeInTheDocument()
  })

  it('leaves ranges from NetBox to NetBox, and has no import of its own (#1347)', async () => {
    const fromNetbox = { ...list.ranges[0], source: 'import' as const, plugin: 'NetBox' }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': { ...list, ranges: [fromNetbox, { ...list.ranges[0], id: 'r2', cidr: '198.51.100.0/24', name: '' }] },
    }).fn)
    renderWithApp(<Firewalls />)
    expect(await screen.findByText('From NetBox')).toBeInTheDocument()
    expect(screen.getByText('Change it in NetBox: the next inventory sync brings it.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Change' })).toHaveLength(1)   // only the range planned here
    expect(screen.queryByRole('button', { name: 'Import from NetBox' })).not.toBeInTheDocument()
  })
})
