import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentSettingsPage, PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { admin, busyAgent } from '@/pages/agents/fixtures'
import { PerAgentSettings } from './PerAgentSettings'

afterEach(() => vi.unstubAllGlobals())

const plugin = { id: 'flows', name: 'NetFlow' } as PluginInfo
const page = (values: Record<string, unknown>): AgentSettingsPage => ({
  fields: [], values: {}, local_only: [], roll_asked: null, renewed_at: null, cert: null, cert_asked: null,
  plugins: [{ id: 'flows', name: 'NetFlow', values,
    fields: [{ key: 'port', label: 'Port', type: 'int', default: 2055, min: 1, max: 65535 }] }],
})

describe('PerAgentSettings', () => {
  it('folds each agent, says what differs on it and saves only the agents that changed', async () => {
    const one = { ...busyAgent(), id: 'a1', name: 'Hall A', tags: [] }
    const two = { ...busyAgent(), id: 'a2', name: 'Hall B', tags: [] }
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/agents/a1/settings': page({ port: 9995 }),
      'GET /api/agents/a2/settings': page({}),
      'PATCH /api/agents/a2/settings': page({ port: 4739 }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PerAgentSettings plugin={plugin} agents={[one, two]} />)
    expect(await screen.findByText('Port: 9995')).toBeInTheDocument()
    expect(await screen.findByText("uses the plugin's settings")).toBeInTheDocument()
    const fold = screen.getByRole('button', { name: /Hall B/ })
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(fold)
    fireEvent.change(screen.getAllByLabelText('Port')[1], { target: { value: '4739' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.filter((c) => c.method === 'PATCH').map((c) => [c.path, c.body]))
      .toEqual([['/api/agents/a2/settings', { plugins: { flows: { port: 4739 } } }]]))
    expect(await screen.findByText('Saved. The agent picks it up on its next pull.')).toBeInTheDocument()
  })

  it('stays away for a plugin with nothing to set per agent', async () => {
    const empty = { ...page({}), plugins: [] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/agents/a1/settings': empty }).fn)
    const { container } = renderWithApp(<PerAgentSettings plugin={plugin} agents={[{ ...busyAgent(), id: 'a1', tags: [] }]} />)
    await vi.waitFor(() => expect(container.querySelector('form')).toBeNull())
  })

  it('sets a value on a tag for every agent with it, and shows what each agent inherits (#1591)', async () => {
    const one = { ...busyAgent(), id: 'a1', name: 'Hall A', tags: ['t2'] }
    const two = { ...busyAgent(), id: 'a2', name: 'Hall B', tags: ['t2'] }
    const tagPage = (values: Record<string, unknown>) => ({ tag: { id: 't2', name: 'Hall 2' }, agents: [], plugins: [{ ...page({}).plugins[0], values }] })
    const inherits = { ...page({}), plugins: [{ ...page({}).plugins[0], inherited: { port: { value: 2060, tag: 't2', name: 'Hall 2' } } }] }
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/inventory/groups': { groups: [], tags: [{ id: 't2', name: 'Hall 2' }] },
      'GET /api/agents/tags/t2/settings': tagPage({ port: 2060 }),
      'PATCH /api/agents/tags/t2/settings': tagPage({ port: 2070 }),
      'GET /api/agents/a1/settings': inherits,
      'GET /api/agents/a2/settings': { ...inherits, plugins: [{ ...inherits.plugins[0], values: { port: 2080 } }] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PerAgentSettings plugin={plugin} agents={[one, two]} />)
    expect(await screen.findByText(/every agent with it: Hall A, Hall B · Port: 2060/)).toBeInTheDocument()
    expect(await screen.findByText('Port: 2060 (tag Hall 2)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Hall B/ }))
    expect(screen.getByText('Differs from tag Hall 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Tag Hall 2/ }))
    fireEvent.change(screen.getAllByLabelText('Port')[0], { target: { value: '2070' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(api.calls.filter((c) => c.method === 'PATCH').map((c) => [c.path, c.body]))
      .toEqual([['/api/agents/tags/t2/settings', { plugins: { flows: { port: 2070 } } }]]))
  })
})
