import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SwitchDetails } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { SwitchPanel } from './SwitchPanel'

afterEach(() => vi.unstubAllGlobals())

const sw: SwitchDetails = {
  name: 'sw-a-01', status: 'online', since: null, model: null, online: 1,
  seats: [{ seat: 'A-1', port: 'Gi1/0/1', state: 'online', problems: 0 }],
  links: [
    { id: 'l1', port: 'Te1/1/1', to: 'dist-01', to_port: 'Te1/0/1', type: 'fiber-mm', speed: 10, issue: '', lldp: { state: 'seen' } },
    { id: 'l2', port: 'Te1/1/2', to: 'dist-02', to_port: 'Te1/0/1', type: 'fiber-mm', speed: 10, issue: '', lldp: { state: 'other', at: 'a', remote: 'dist-01', remote_port: 'Te1/0/7' } },
  ],
  neighbours: [{ port: 'Gi1/0/48', remote: 'desk-switch', remote_port: 'Gi0/1', protocol: 'cdp' }],
}

describe('SwitchPanel', () => {
  it('lists the uplinks with what LLDP sees, and neighbours no uplink explains', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/plan/switches/sw-a-01': sw }).fn)
    renderWithApp(<SwitchPanel name="sw-a-01" onSeat={() => {}} onClose={() => {}} />)
    const uplinks = await screen.findByRole('table', { name: 'Uplinks' })
    expect(uplinks).toHaveTextContent('dist-01 Te1/0/1')
    expect(uplinks).toHaveTextContent('Seen')
    expect(uplinks).toHaveTextContent('Sees dist-01 Te1/0/7: check the patch')
    expect(screen.getByText('Also seen by LLDP/CDP')).toBeInTheDocument()
    expect(screen.getByText('desk-switch Gi0/1')).toBeInTheDocument()
  })
})
