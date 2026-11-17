import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import PluginSettings from './PluginSettings'

const plugin: PluginInfo = {
  id: 'http-check', name: 'HTTP check', version: '1.0.0', description: 'Checks web services.', trust: 'builtin',
  author: '', homepage: '', uses: [{ id: 'http', label: 'Make HTTP requests' }], enabled: true, error: null,
  settings_section: 'plugin-http-check', actions: [{ id: 'reset', label: 'Reset', role: 'admin', danger: true }],
  widgets: [], endpoints: [], hooks: [], has_test: true,
}
const settings = {
  sections: [{ id: 'plugin-http-check', title: 'Plugin: HTTP check', description: 'Web services.' },
    { id: 'cache', title: 'Caching', description: 'TTL.' }],
  fields: [{ key: 'plugin.http-check.timeout', section: 'plugin-http-check', label: 'Timeout', type: 'int', env: null, min: 1, max: 60 },
    { key: 'cache.ttl_arp', section: 'cache', label: 'ARP table TTL', type: 'int', env: 'CACHE_TTL_ARP' }],
  values: { 'plugin.http-check.timeout': { source: 'default', value: 5 }, 'cache.ttl_arp': { source: 'default', value: 300 } },
  status: { netbox_enabled: false, librenms_enabled: false, redis: null },
}
const page = (id = 'http-check') =>
  renderWithApp(<Routes><Route path="/settings/plugins/:id" element={<PluginSettings />} /></Routes>, `/settings/plugins/${id}`)

afterEach(() => vi.unstubAllGlobals())

describe('A plugin page', () => {
  it('shows only its own settings and saves them', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [plugin] },
      'GET /api/settings': settings, 'PUT /api/settings': settings,
    })
    vi.stubGlobal('fetch', api.fn)
    page()
    expect(await screen.findByRole('heading', { name: 'HTTP check', level: 1 })).toBeInTheDocument()
    expect(screen.queryByLabelText('ARP table TTL')).toBeNull()
    fireEvent.change(await screen.findByLabelText('Timeout'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ 'plugin.http-check.timeout': 10 }))
  })

  it('asks before a dangerous action', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [plugin] },
      'GET /api/settings': settings,
      'POST /api/plugins/http-check/actions/reset': { ok: true, message: 'Reset done', data: {} },
    })
    vi.stubGlobal('fetch', api.fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Reset' }))
    expect(api.calls.some((c) => c.method === 'POST')).toBe(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(screen.getByText('✓ Reset done')).toBeInTheDocument())
  })

  it('says so for an unknown plugin', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null }, 'GET /api/settings/plugins': { plugins: [plugin] }, 'GET /api/settings': settings,
    }).fn)
    page('nope')
    expect(await screen.findByText('There is no plugin "nope".')).toBeInTheDocument()
  })
})
