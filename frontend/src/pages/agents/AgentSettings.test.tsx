import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Agent, AgentSettingsPage } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { AgentSettingsForm, CertPanel, KeyPanel } from './AgentSettings'
import { admin, busyAgent } from './fixtures'

afterEach(() => vi.unstubAllGlobals())

const page = (over: Partial<AgentSettingsPage> = {}): AgentSettingsPage => ({
  fields: [
    { key: 'lan_url', env: 'FLOORBIT_AGENT_LAN_URL', type: 'url', default: '', restart: false },
    { key: 'telemetry_port', env: 'FLOORBIT_TELEMETRY_PORT', type: 'int', default: 8186, restart: true, min: 1, max: 65535 },
    { key: 'metrics', env: 'FLOORBIT_AGENT_METRICS', type: 'listen', default: '0.0.0.0:9520', restart: true },
    { key: 'metrics_token', env: 'FLOORBIT_AGENT_METRICS_TOKEN', type: 'secret', default: '', restart: true },
  ],
  values: { lan_url: 'http://192.0.2.10:8908', metrics_token: true },
  local_only: ['FLOORBIT_AGENT_ALLOW_ACTIONS', 'FLOORBIT_AGENT_SWITCH_NETS'],
  plugins: [{ id: 'flows', name: 'NetFlow', values: {},
    fields: [{ key: 'port', label: 'Port', type: 'int', default: null, min: 1, max: 65535 }] }],
  roll_asked: null, renewed_at: null, cert: null, cert_asked: null, ...over,
})

function agent(): Agent {
  const a = busyAgent()
  return { ...a, report: { ...a.report!, settings: {
    values: {
      lan_url: { source: 'floorbit', value: 'http://192.0.2.10:8908' },
      telemetry_port: { source: 'env', value: '9000' },
      metrics: { source: 'default', value: '0.0.0.0:9520' },
      metrics_token: { source: 'floorbit', set: true },
      FLOORBIT_AGENT_ALLOW_ACTIONS: { source: 'env', value: 'no' },
    },
    pending: ['metrics_token'], key: 'stored',
    cert: { not_after: Date.now() / 1000 + 86400 * 300, names: ['agent.example.com'], source: 'floorbit', floorbit_ca: true },
  } } }
}

describe('AgentSettingsForm', () => {
  it('shows where each value comes from, locks what the agent sets itself and saves the changes', async () => {
    const a = agent()
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      [`GET /api/agents/${a.id}/settings`]: page(),
      [`PATCH /api/agents/${a.id}/settings`]: page({ plugins: [{ ...page().plugins[0], values: { port: 2055 } }] }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<AgentSettingsForm agent={a} />)
    const port = await screen.findByLabelText(/Telemetry port/)
    expect(port).toBeDisabled()
    expect(port).toHaveValue('9000')
    expect(screen.getByText('Set on the agent by FLOORBIT_TELEMETRY_PORT, which wins over Floorbit.')).toBeInTheDocument()
    expect(screen.getByText('at next start')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Set (type to replace)')).toBeInTheDocument()
    const hall = screen.getByRole('table', { name: 'Limits set in the hall' })
    expect(within(hall).getByText('no')).toBeInTheDocument()
    expect(within(hall).getByText('not set')).toBeInTheDocument()

    expect(screen.getByRole('button', { name: 'Save 0 changes' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Address in the hall/), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText(/^Port/), { target: { value: '2055' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save 2 changes' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body)
      .toEqual({ settings: { lan_url: null }, plugins: { flows: { port: 2055 } } }))
    expect(await screen.findByRole('button', { name: 'Save 0 changes' })).toBeDisabled()
  })
})

describe('KeyPanel and CertPanel', () => {
  it('rolls the key and asks for a certificate for the listed names', async () => {
    const a = agent()
    const p = page({ values: { cert_names: ['agent.example.com'] }, roll_asked: Date.now() / 1000 - 60 })
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      [`POST /api/agents/${a.id}/roll`]: { ok: true },
      [`POST /api/agents/${a.id}/cert`]: { ok: true },
      [`PATCH /api/agents/${a.id}/settings`]: page({ values: { cert_names: ['agent.example.com', '192.0.2.10'] } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<><KeyPanel agent={a} page={p}><span /></KeyPanel><CertPanel agent={a} page={p} /></>)
    expect(screen.getByText(/fetched from Floorbit/)).toBeInTheDocument()
    expect(screen.getByText(/New key waiting for the agent since/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Roll key' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Roll key' })).getByRole('button', { name: 'Yes, go ahead' }))
    await vi.waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path.endsWith('/roll'))).toBe(true))
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())   // after its closing transition

    expect(screen.getByText(/For agent\.example\.com, valid until/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download CA' })).toHaveAttribute('href', '/api/agents/ca.pem')
    fireEvent.click(screen.getByRole('button', { name: 'New certificate' }))
    await vi.waitFor(() => expect(api.calls.some((c) => c.path.endsWith('/cert'))).toBe(true))
    const names = screen.getAllByLabelText('Names on the certificate').find((e) => e.tagName === 'INPUT' && e.getAttribute('type') !== 'hidden')!
    await userEvent.type(names, '192.0.2.10{Enter}')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body)
      .toEqual({ settings: { cert_names: ['agent.example.com', '192.0.2.10'] } }))
  })

  it('shows the pinned key and resets it', async () => {
    const a = agent()
    const now = Date.now() / 1000
    const p = page({ identity: { fingerprint: 'ab12cd34ef56ab12cd34ef56ab12cd34', pinned_at: now - 86400, issued_at: now - 86400, not_after: now + 89 * 86400 } })
    const api = fakeFetch({ 'GET /api/auth/me': admin, [`POST /api/agents/${a.id}/identity/reset`]: page() })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<KeyPanel agent={a} page={p}><span /></KeyPanel>)
    expect(screen.getByText(/Signs every request with its own key ab12cd34ef56ab12/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reset identity' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Reset identity' })).getByRole('button', { name: 'Yes, go ahead' }))
    await vi.waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path.endsWith('/identity/reset'))).toBe(true))
  })

  it('says when no key is pinned yet', () => {
    renderWithApp(<KeyPanel agent={agent()} page={page({ identity: null })}><span /></KeyPanel>)
    expect(screen.getByText(/No own key pinned yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reset identity' })).not.toBeInTheDocument()
  })
})
