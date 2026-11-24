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
    { key: 'log_level', env: 'FLOORBIT_AGENT_LOG_LEVEL', type: 'choice', default: 'info', options: ['debug', 'info', 'warning', 'error'], restart: false },
    { key: 'telemetry_port', env: 'FLOORBIT_TELEMETRY_PORT', type: 'int', default: 8186, restart: true, min: 1, max: 65535 },
    { key: 'metrics', env: 'FLOORBIT_AGENT_METRICS', type: 'listen', default: '0.0.0.0:9520', restart: true },
    { key: 'metrics_token', env: 'FLOORBIT_AGENT_METRICS_TOKEN', type: 'secret', default: '', restart: true },
  ],
  values: { log_level: 'debug', metrics_token: true },
  local_only: ['FLOORBIT_AGENT_ALLOW_ACTIONS', 'FLOORBIT_AGENT_SWITCH_NETS'],
  plugins: [{ id: 'flows', name: 'NetFlow', values: {},
    fields: [{ key: 'port', label: 'Port', type: 'int', default: null, min: 1, max: 65535 }] }],
  roll_asked: null, renewed_at: null, cert: null, cert_asked: null, ...over,
})

function agent(): Agent {
  const a = busyAgent()
  return { ...a, report: { ...a.report!, settings: {
    values: {
      log_level: { source: 'floorbit', value: 'debug' },
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
  it('puts the few settings that differ first, says where a value comes from and saves through the save bar', async () => {
    const a = agent()
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': { agents: [a], connected: true, max: 4 },
      [`GET /api/agents/${a.id}/settings`]: page(),
      [`PATCH /api/agents/${a.id}/settings`]: page(),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<AgentSettingsForm agent={a} />)
    const port = await screen.findByLabelText('Telemetry port')
    expect(port).toBeDisabled()
    expect(port).toHaveValue('9000')
    expect(screen.getByText("Set by the agent's environment")).toBeInTheDocument()
    expect(screen.getByText('Set here')).toBeInTheDocument()
    // No env var name stands on the page; it sits in a tooltip.
    expect(screen.queryByText(/FLOORBIT_/)).toBeNull()
    fireEvent.mouseEnter(screen.getByText("Set by the agent's environment").closest('span') as HTMLElement)
    expect(await screen.findByText(/environment variable FLOORBIT_TELEMETRY_PORT/)).toBeInTheDocument()

    // Metrics fold under Advanced; with one agent there are no shared addresses.
    const toggle = screen.getByRole('button', { name: /Advanced: 2 more/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(screen.getByPlaceholderText('Set (type to replace)')).toBeInTheDocument()
    expect(screen.getByText('at next start')).toBeInTheDocument()

    expect(screen.getByText('Actions that change the hall')).toBeInTheDocument()
    expect(screen.getByText('no')).toBeInTheDocument()
    expect(screen.getByText('private addresses only')).toBeInTheDocument()
    // Plugin values that differ per agent are set on the plugin's page (#990).
    expect(screen.getByText("Uses the plugin's settings.")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Set on the plugin page' })).toHaveAttribute('href', '/settings/plugins/flows?tab=agents')

    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByText('1 unsaved change')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'PATCH')?.body)
      .toEqual({ settings: { log_level: null } }))
    expect(await screen.findByText('Saved. The agent picks it up on its next pull.')).toBeInTheDocument()
  })

  it('shows the shared addresses once there is a second agent', async () => {
    const a = agent()
    const vrrpPage = page({ fields: [...page().fields, { key: 'vrrp_vips', env: 'FLOORBIT_AGENT_VRRP_VIPS', type: 'cidrs', default: [], restart: true }] })
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents': { agents: [a, { ...a, id: 'b', name: 'Agent B' }], connected: true, max: 4 },
      [`GET /api/agents/${a.id}/settings`]: vrrpPage,
    }).fn)
    renderWithApp(<AgentSettingsForm agent={a} />)
    expect(await screen.findByRole('button', { name: /Advanced: 3 more/ })).toBeInTheDocument()
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

  it("shows the tenant's Let's Encrypt certificate and why it is missing", () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin }).fn)
    const a = agent()
    const good = page({ public_cert: { name: 'club.agent.example.com', not_after: Date.now() / 1000 + 86400 * 60,
      issued_at: Date.now() / 1000, error: null, failed_at: null } })
    const { unmount } = renderWithApp(<CertPanel agent={a} page={good} />)
    expect(screen.getByText(/Let's Encrypt: club\.agent\.example\.com, valid until/)).toBeInTheDocument()
    unmount()
    const failed = page({ public_cert: { name: 'club.agent.example.com', not_after: null, issued_at: null,
      error: 'Connection refused on port 80', failed_at: Date.now() / 1000 } })
    const second = renderWithApp(<CertPanel agent={a} page={failed} />)
    expect(screen.getByText(/could not issue club\.agent\.example\.com yet: Connection refused on port 80/)).toBeInTheDocument()
    second.unmount()
    const notYet = page({ public_cert: { name: 'club.agent.example.com', not_after: null, issued_at: null,
      error: null, failed_at: null, waiting: 'http://club.agent.example.com cannot be reached (ConnectionError).', checked_at: 1 } })
    renderWithApp(<CertPanel agent={a} page={notYet} />)
    expect(screen.getByText(/waiting until club\.agent\.example\.com reaches Floorbit/)).toBeInTheDocument()
  })
})
