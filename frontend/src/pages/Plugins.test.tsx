import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Plugins, { PluginCard } from './Plugins'

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
    expect(screen.getByRole('link', { name: 'HTTP check' })).toHaveAttribute('href', '/settings/plugins/http-check')
    expect(within(screen.getByRole('list')).getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings/plugins/http-check')
    expect(screen.getByText('Ships with Floorbit')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('switch'))
    expect(await screen.findByText('✓ HTTP check is on.')).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ enabled: true })
  })

  it('says where its data stands against the schema it knows', () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    const cases: [Partial<PluginInfo>, RegExp][] = [
      [{ schema: 2, data_schema: 2 }, /^Its data: schema 2$/],
      [{ schema: 2, data_schema: 1 }, /at schema 1 and moves to 2 when the plugin next runs/],
      [{ schema: 1, data_schema: 3 }, /at schema 3, newer than this version knows \(1\)/],
    ]
    for (const [extra, text] of cases) {
      const { unmount } = renderWithApp(<PluginCard plugin={{ ...plugin, ...extra }} />)
      expect(screen.getByText(text)).toBeInTheDocument()
      unmount()
    }
    renderWithApp(<PluginCard plugin={plugin} />)
    expect(screen.queryByText(/schema/)).toBeNull()
  })

  it('filters a long list', async () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ ...plugin, id: `p${i}`, name: `Plugin ${i}`, enabled: i < 3 }))
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [...many, { ...plugin, name: 'Shelly meters', id: 'shelly' }] },
    }).fn)
    renderWithApp(<Plugins />)
    fireEvent.change(await screen.findByLabelText('Search plugins'), { target: { value: 'shelly' } })
    expect(within(screen.getByRole('list')).getAllByRole('heading').map((h) => h.textContent)).toEqual(['Shelly meters'])
    fireEvent.change(screen.getByLabelText('Search plugins'), { target: { value: '' } })
    fireEvent.click(within(screen.getByRole('radiogroup')).getByText('On'))
    await waitFor(() => expect(within(screen.getByRole('list')).getAllByRole('heading')).toHaveLength(3))
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

  it('opens the marketplace in its own tab', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [plugin] },
      'GET /api/settings/marketplace': { sources: [], plugins: [] },
    }).fn)
    renderWithApp(<Plugins />)
    fireEvent.click(await screen.findByRole('tab', { name: 'Marketplace' }))
    expect(await screen.findByRole('heading', { name: 'Marketplace', level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'HTTP check' })).toBeNull()
  })
})
