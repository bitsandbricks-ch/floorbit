import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { FirewallList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Firewalls from './Firewalls'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const list: FirewallList = {
  firewalls: [
    { id: 'f1', name: 'fw-01', model: 'Example FW', hall: '', status: 'online', serving: ['192.0.2.0/27', '192.0.2.32/27'], planned: ['192.0.2.0/27'], backup_for: ['192.0.2.32/27'], seats: 40 },
    { id: 'f2', name: 'fw-02', model: '', hall: '', status: 'offline', serving: [], planned: ['192.0.2.32/27'], backup_for: [], seats: 0 },
  ],
  ranges: [
    { id: 'r1', cidr: '192.0.2.0/27', name: 'Block A', firewalls: ['fw-01', 'fw-02'], intended: 'fw-01', now: 'fw-01', state: 'primary', seats: 22 },
    { id: 'r2', cidr: '192.0.2.32/27', name: '', firewalls: ['fw-02', 'fw-01'], intended: 'fw-02', now: 'fw-01', state: 'failover', seats: 18 },
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
    expect(screen.getByText('192.0.2.32/27 runs over fw-01, planned fw-02')).toBeInTheDocument()
    expect(screen.getByText('fw-02 → fw-01')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add range' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change' })).not.toBeInTheDocument()
  })

  it('lets the crew add a range with its firewalls in order', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': { ...list, ranges: [] },
      'POST /api/firewalls/ranges': () => ({ status: 201, body: list.ranges[0] }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Firewalls />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add range' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Range' }), { target: { value: '192.0.2.0/27' } })
    const [line] = screen.getAllByLabelText('Firewalls in order').filter((el) => el.tagName === 'INPUT' && el.getAttribute('type') !== 'hidden')
    fireEvent.click(line)
    fireEvent.click(await screen.findByRole('option', { name: 'fw-02', hidden: true }))
    fireEvent.click(await screen.findByRole('option', { name: 'fw-01', hidden: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      cidr: '192.0.2.0/27', name: '', firewalls: ['fw-02', 'fw-01'],
    }))
  })

  it('splits a network over all firewalls and says how many ranges that makes', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/firewalls': { ...list, ranges: [] },
      'POST /api/firewalls/ranges/split': () => ({ status: 201, body: { added: 4, skipped: 0, ranges: [] } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Firewalls />)
    fireEvent.click(await screen.findByRole('button', { name: 'Split a network' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Network' }), { target: { value: '198.51.100.0/22' } })
    expect(screen.getByText('Makes 4 ranges.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Hall' } })
    fireEvent.click(screen.getByRole('button', { name: 'Split' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      cidr: '198.51.100.0/22', size: 24, name: 'Hall', firewalls: ['fw-01', 'fw-02'],
    }))
  })

  it('refuses a split into more than 256 ranges before asking the server', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/firewalls': list }).fn)
    renderWithApp(<Firewalls />)
    fireEvent.click(await screen.findByRole('button', { name: 'Split a network' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Network' }), { target: { value: '198.51.0.0/15' } })
    expect(screen.getByText('That makes more than 256 ranges: pick a larger range size.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Split' })).toBeDisabled()
  })
})
