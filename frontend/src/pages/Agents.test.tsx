import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Agents from './Agents'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const agent: Agent = {
  id: 'a1b2c3d4', name: 'Spring LAN, hall 2', created_at: 1_790_000_000, created_by: 'ada',
  last_seen: Date.now() / 1000 - 5, version: '0.9.0', address: null, connected: true,
}

describe('Agents', () => {
  it('lists agents, enrols one and shows its key and how to start it', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': { agents: [agent, { ...agent, id: 'b', name: 'Old site', connected: false, last_seen: null, version: null }], connected: true, max: 10 },
      'POST /api/agents': { ...agent, id: 'e5f6a7b8', name: 'Autumn LAN', connected: false, last_seen: null, key: 'fba_e5f6a7b8_example-key-0123456789' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText('Spring LAN, hall 2')).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.getByText('Not connected')).toBeInTheDocument()
    expect(screen.getByText(/never connected/)).toBeInTheDocument()
    expect(screen.getByText(/version 0\.9\.0/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Autumn LAN' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enrol' }))
    expect(await screen.findByText('fba_e5f6a7b8_example-key-0123456789')).toBeInTheDocument()
    expect(screen.getByText(/FLOORBIT_AGENT_KEY=fba_e5f6a7b8_example-key-0123456789/)).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'Autumn LAN' })
  })
  it('says the plugins answer while there is no agent', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Agents />)
    expect(await screen.findByText(/No agent yet/)).toBeInTheDocument()
  })
})
