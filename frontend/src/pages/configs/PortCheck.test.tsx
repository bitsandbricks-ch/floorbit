import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PortCheckPanel, type PortCheck } from './PortCheck'

afterEach(() => vi.unstubAllGlobals())

const rules = [
  { id: 'portfast', label: 'PortFast', fix: '' }, { id: 'bpduguard', label: 'BPDU guard', fix: '' },
  { id: 'storm', label: 'storm control', fix: '' }, { id: 'access', label: 'access mode', fix: '' },
  { id: 'vlan', label: 'One access VLAN', fix: '' },
]
const check: PortCheck = {
  switches: [
    { switch: 'sw-a-01', copy: { id: 'c1', at: 1_763_000_000 }, seat_ports: 5, checked: 5, findings: [
      { rule: 'bpduguard', label: 'BPDU guard', ports: ['Gi1/0/2 - 3'], count: 2,
        fix: ['interface range Gi1/0/2 - 3', ' spanning-tree bpduguard enable'] },
      { rule: 'vlan', label: 'VLAN 100', ports: ['Gi1/0/4'], count: 1, vlan: 100, fix: ['interface range Gi1/0/4', ' switchport access vlan 100'] },
    ] },
    { switch: 'sw-a-02', copy: { id: 'c2', at: 1_763_000_000 }, seat_ports: 4, checked: 4, findings: [] },
  ],
  no_copy: ['sw-b-01'], off: [], rules,
}

describe('Seat port check', () => {
  it('lists the ports that break a rule with the config that fixes them', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/configs/port-check': check }).fn)
    renderWithApp(<PortCheckPanel />)
    expect(await screen.findByText('2 ports without BPDU guard')).toBeInTheDocument()
    expect(screen.getByText('1 port not in VLAN 100')).toBeInTheDocument()
    expect(screen.getByText(/2 switches with seat ports checked, 1 fine/)).toBeInTheDocument()
    expect(screen.getByText(/No config copy yet: sw-b-01/)).toBeInTheDocument()
    expect(screen.getByText(/spanning-tree bpduguard enable/)).toBeInTheDocument()
  })

  it('turns a rule off for the event', async () => {
    const api = fakeFetch({ 'GET /api/configs/port-check': check, 'PUT /api/configs/port-check': { ...check, off: ['storm'] } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PortCheckPanel />)
    fireEvent.click(await screen.findByRole('checkbox', { name: 'storm control' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ off: ['storm'] }))
  })
})
