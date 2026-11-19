import { fireEvent, screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import AgentDetail from './AgentDetail'
import { admin, busyAgent } from './agents/fixtures'

afterEach(() => vi.unstubAllGlobals())

const halls = { halls: [{ id: 'main', name: 'Main hall' }, { id: 'h2', name: 'Hall 2' }] }

function open(agent: Agent, tab = '', extra: Record<string, unknown> = {}) {
  const api = fakeFetch({
    'GET /api/auth/me': admin, 'GET /api/halls': halls,
    'GET /api/agents': { agents: [agent], connected: true, max: 10, protocol: 2, newest_version: agent.version },
    ...extra,
  })
  vi.stubGlobal('fetch', api.fn)
  renderWithApp(
    <Routes><Route path="/settings/agents/:id" element={<AgentDetail />} /><Route path="/settings/agents" element={<p>list</p>} /></Routes>,
    `/settings/agents/${agent.id}${tab ? `?tab=${tab}` : ''}`,
  )
  return api
}

describe('AgentDetail', () => {
  it('shows what it is, what needs a look and its plugins', async () => {
    const api = open(busyAgent(), '', { 'POST /api/agent-plugins/a1b2c3d4/telemetry/unblock': { ok: true, cleared: 1 } })
    expect(await screen.findByRole('heading', { name: 'Spring LAN, hall 2', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('Online, with errors')).toBeInTheDocument()
    expect(screen.getByText('up 3 hours')).toBeInTheDocument()
    for (const chip of ['Version 0.9.0', 'WebSocket (wss)', '192.0.2.20', 'Hall 2', 'protocol 2']) {
      expect(screen.getAllByText(chip).length).toBeGreaterThan(0)
    }
    const look = screen.getByRole('region', { name: 'Needs a look' })
    expect(within(look).getByText('telemetry is failing: cannot listen on 8186')).toBeInTheDocument()
    expect(within(look).getByText(/netbox is not running: this agent does not have this plugin/)).toBeInTheDocument()
    expect(within(look).getByText(/2 calls failed in the last hour, last .*: port_stats: LibreNMS said no/)).toBeInTheDocument()
    expect(within(look).getByText('3 syslog lines dropped')).toBeInTheDocument()
    expect(within(look).getByText(/Login to sw-a-01 with ssh-ops failed .*\(Authentication failed\)/)).toBeInTheDocument()
    fireEvent.click(within(look).getByRole('button', { name: 'Clear, try again' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.path.includes('/unblock'))?.body).toEqual({ device: 'sw-a-01', credential: 'ssh-ops' }))
    const table = screen.getByRole('table', { name: 'Agent plugins' })
    expect(within(table).getByText('lines 52,000 · backlog 0')).toBeInTheDocument()
    expect(within(table).getByText(/: port in use/)).toBeInTheDocument()
    expect(screen.getByText(/syslog 12,345 received, 0 waiting/)).toBeInTheDocument()
    expect(screen.getByText(/check-in note 1,200 shown, 3,400 not needed/)).toBeInTheDocument()
    expect(screen.getByText('Syslog, NetFlow')).toBeInTheDocument()
  })

  it('shows its plugin updates', async () => {
    const now = Date.now() / 1000
    const a: Agent = { ...busyAgent(), report: { at: now, plugins: {},
      updates: { policy: 'approve', image: '0.4.0', signed: true,
        plugins: { lancache: { version: '0.5.0', source: 'bundle', probation: true, rolled_back: [], pending: null },
                   netbox: { version: '0.4.0', source: 'image', probation: false, rolled_back: [], pending: { version: '0.5.0', why: 'waits for approval on the agent' } } },
        events: [{ at: now - 60, plugin: 'lancache', event: 'installed', version: '0.5.0', detail: 'was 0.4.0' },
                 { at: now - 30, plugin: 'telemetry', event: 'rolled back', version: '0.5.0', detail: 'cannot start' }] } } }
    open(a, 'updates')
    expect(await screen.findByText(/Plugin updates wait for approval on the agent · image 0\.4\.0/)).toBeInTheDocument()
    expect(screen.getByText('lancache runs 0.5.0 (update) · being watched')).toBeInTheDocument()
    expect(screen.getByText('netbox 0.5.0 offered: waits for approval on the agent')).toBeInTheDocument()
    expect(screen.getByText('rolled back')).toBeInTheDocument()
    expect(screen.getByText(/telemetry 0\.5\.0 · .* · cannot start/)).toBeInTheDocument()
  })

  it('changes its settings: a new key, a new name, its halls, revoke', async () => {
    const a = { ...busyAgent(), plugins_off: ['shelly'] }
    const api = open(a, 'settings', {
      [`POST /api/agents/${a.id}/rotate`]: { id: a.id, name: a.name, key: 'fba_a1b2c3d4_another-example-key-012345' },
      [`PATCH /api/agents/${a.id}`]: { id: a.id },
      [`DELETE /api/agents/${a.id}`]: { ok: true },
    })
    expect(await screen.findByText('Plugins it leaves off')).toBeInTheDocument()
    expect(await screen.findByText('Answers for')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'New key' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    expect(await screen.findByText('fba_a1b2c3d4_another-example-key-012345')).toBeInTheDocument()
    expect(screen.getByText(`New key for ${a.name}`)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }))
    fireEvent.change(screen.getByLabelText('New name'), { target: { value: 'Hall 2 agent' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: 'Hall 2 agent' }))
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    expect(await screen.findByText('list')).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'DELETE')).toBe(true)
  })

  it('says when the agent is gone', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/halls': halls, 'GET /api/agents': { agents: [], connected: false, max: 10 } }).fn)
    renderWithApp(<Routes><Route path="/settings/agents/:id" element={<AgentDetail />} /></Routes>, '/settings/agents/nope')
    expect(await screen.findByText('No such agent')).toBeInTheDocument()
  })
})
