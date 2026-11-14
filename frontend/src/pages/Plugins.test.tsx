import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Plugins from './Plugins'

const plugin: PluginInfo = {
  id: 'http-check',
  name: 'HTTP check',
  version: '1.0.0',
  description: 'Checks web services.',
  trust: 'builtin',
  author: '',
  homepage: '',
  uses: [{ id: 'http', label: 'Make HTTP requests' }],
  enabled: false,
  error: null,
  settings_section: 'plugin-http-check',
  actions: [{ id: 'check', label: 'Check now', role: 'editor' }],
  widgets: [],
  endpoints: [],
  hooks: [],
  has_test: true,
}

afterEach(() => vi.unstubAllGlobals())

describe('Plugins page', () => {
  it('lists plugins and turns one on', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'admin', display_name: 'Admin', role: 'admin' } },
      'GET /api/settings/plugins': { plugins: [plugin] },
      'PUT /api/settings/plugins/http-check': { plugins: [{ ...plugin, enabled: true }], name: 'HTTP check' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Plugins />)

    expect(await screen.findByRole('heading', { name: 'HTTP check' })).toBeInTheDocument()
    expect(screen.getByText('Ships with Floorbit')).toBeInTheDocument()
    // Off: no test or action buttons yet.
    expect(screen.queryByRole('button', { name: 'Test' })).toBeNull()

    fireEvent.click(screen.getByRole('switch'))
    expect(await screen.findByText('✓ HTTP check is on.')).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ enabled: true })
    expect(screen.getByRole('button', { name: 'Test' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check now' })).toBeInTheDocument()
  })

  it('shows a plugin that failed to load and keeps its switch off', async () => {
    vi.stubGlobal(
      'fetch',
      fakeFetch({
        'GET /api/auth/me': { enabled: false, user: null },
        'GET /api/settings/plugins': { plugins: [{ ...plugin, error: 'plugin.py: syntax error' }] },
      }).fn,
    )
    renderWithApp(<Plugins />)
    expect(await screen.findByRole('alert')).toHaveTextContent('plugin.py: syntax error')
    expect(screen.getByRole('switch')).toBeDisabled()
  })

  it('asks before a dangerous action', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': {
        plugins: [{ ...plugin, enabled: true, actions: [{ id: 'reset', label: 'Reset', role: 'admin', danger: true }] }],
      },
      'POST /api/plugins/http-check/actions/reset': { ok: true, message: 'Reset done', data: {} },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Plugins />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reset' }))
    expect(api.calls.some((c) => c.method === 'POST')).toBe(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(screen.getByText('✓ Reset done')).toBeInTheDocument())
  })
})
