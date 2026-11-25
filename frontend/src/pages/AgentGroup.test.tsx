import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentGroupDetail, AgentGroupMember } from '@/api/agentGroups'
import { fakeFetch, renderWithApp } from '@/test/render'
import AgentGroup from './AgentGroup'
import { admin } from './agents/fixtures'

afterEach(() => vi.unstubAllGlobals())

const member = (over: Partial<AgentGroupMember>): AgentGroupMember => ({
  id: 'a', name: 'Rack A', connected: true, role: 'primary', holds: [], address: '', version: '0.9.0',
  follows_split: true, owns: 0, pinned: 0, capabilities: ['lease', 'split', 'syslog_hold'], ...over,
})

function open(group: Partial<AgentGroupDetail>) {
  const answer: AgentGroupDetail = {
    id: 'hall-1', tags: ['hall-1'], label: 'Main hall', state: 'ok', mode: 'active-active', primary: 'a',
    vips: [], split: true, devices: 0, agents: [], ...group,
  }
  vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents/groups/hall-1': answer }).fn)
  renderWithApp(<Routes><Route path="/settings/agents/groups/:gid" element={<AgentGroup />} /></Routes>, '/settings/agents/groups/hall-1')
}

describe('AgentGroup', () => {
  it('shows each agent, its share of the devices and the shared addresses', async () => {
    open({
      devices: 400, vips: ['192.0.2.10', '192.0.2.11'],
      agents: [
        member({ owns: 210, pinned: 2, holds: ['192.0.2.10'] }),
        member({ id: 'b', name: 'Rack B', role: 'standby', owns: 188, holds: ['192.0.2.11'] }),
      ],
    })
    expect(await screen.findByRole('heading', { name: 'Main hall', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('Failover ready')).toBeInTheDocument()
    const a = screen.getByRole('article', { name: 'Rack A' })
    expect(within(a).getByText('210 of 400')).toBeInTheDocument()
    expect(within(a).getByRole('link', { name: 'Rack A' })).toHaveAttribute('href', '/settings/agents/a')
    expect(screen.getAllByText('Rack B · 188').length).toBeGreaterThan(0)
    expect(screen.getByText(/Each device belongs to one agent/)).toBeInTheDocument()
    expect(screen.getByText('When Rack A stops, its 210 devices move to the others. The rest stay where they are.')).toBeInTheDocument()
    expect(screen.getByText(/2 devices are pinned/)).toBeInTheDocument()
    const vips = screen.getByRole('table', { name: 'Shared addresses' })
    expect(within(vips).getByText('192.0.2.11').closest('tr')).toHaveTextContent('Rack B')
  })

  it('says which agent keeps the group from splitting', async () => {
    open({
      split: false, devices: 100,
      agents: [member({ owns: 100 }), member({ id: 'b', name: 'Rack B', role: 'standby', follows_split: false, capabilities: ['lease'] })],
    })
    expect(await screen.findByText(/Rack B can't follow it yet/)).toBeInTheDocument()
    const b = within(screen.getByRole('article', { name: 'Rack B' })).getByLabelText('Capabilities')
    expect(within(b).getByText('Falls back to one primary collecting every device of the group.')).toBeInTheDocument()
    expect(within(b).getByText('Polls and logs in only while Floorbit says it is the primary.')).toBeInTheDocument()
    expect(screen.getByText('No shared addresses. Without them, give the check-in name every agent\'s address in the event DNS.')).toBeInTheDocument()
  })
})
