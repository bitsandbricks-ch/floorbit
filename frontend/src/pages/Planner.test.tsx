import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlannerData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Planner from './Planner'
import { seatRange } from './planner/seats'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const settings = {
  model: 'cisco-ios', access_ports: 48, uplink_ports: 2, spare: 2, vlan_mode: 'block' as const, vlan_base: 100,
  name: 'sw-{block}-{n:02d}', mgmt_net: '198.51.100.0/24', mgmt_first: 11, mgmt_gateway: '198.51.100.1', mgmt_vlan: 10,
}
const port = (n: number, seat: string) => ({ n, name: `GigabitEthernet1/0/${n}`, seat, vlan: 101 })
const data: PlannerData = {
  models: [{ id: 'cisco-ios', label: 'Cisco IOS (Catalyst)', access: 'GigabitEthernet1/0/{n}', uplink: 'GigabitEthernet1/1/{u}', builtin: true }],
  plan: {
    settings, model: { id: 'cisco-ios', label: 'Cisco IOS (Catalyst)', access: 'GigabitEthernet1/0/{n}', uplink: 'GigabitEthernet1/1/{u}' },
    blocks: [{ name: 'B', hall: 'Main hall', seats: 2, vlan: 101, switches: ['sw-b-01'] }],
    switches: [{
      name: 'sw-b-01', block: 'B', hall_id: 'main', hall: 'Main hall', vlan: 101, mgmt_ip: '198.51.100.11', exists: false,
      ports: [port(1, 'B-1'), port(2, 'B-2')], spare: [{ n: 3, name: 'GigabitEthernet1/0/3' }], uplinks: [{ n: 1, name: 'GigabitEthernet1/1/1' }],
    }],
    vlans: [{ id: 101, name: 'block-B' }], problems: [],
    totals: { seats: 2, switches: 1, new: 1, vlans: 1, uplinks: 2 },
  },
}

describe('Build planner', () => {
  it('writes a switch\'s seats as one run', () => {
    expect(seatRange(['A-1', 'A-2', 'A-46'])).toBe('A-1 – A-46')
    expect(seatRange([])).toBe('–')
  })

  it('shows the plan, a config, and adds the new switches', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/planner': data,
      'GET /api/planner/config/sw-b-01': { name: 'sw-b-01', config: 'hostname sw-b-01' },
      'POST /api/planner/apply': { added: ['sw-b-01'] },
      'PUT /api/planner/settings': settings,
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Planner />)
    expect(await screen.findByText('sw-b-01')).toBeInTheDocument()
    expect(screen.getByText('B-1 – B-2')).toBeInTheDocument()
    expect(screen.getByText('198.51.100.11')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Config' }))
    expect(await screen.findByText('hostname sw-b-01')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 switch to the floor plan' }))
    expect(await screen.findByText('Added sw-b-01 to the floor plan.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT' && c.path === '/api/planner/settings')).toBe(true))
  })
})
