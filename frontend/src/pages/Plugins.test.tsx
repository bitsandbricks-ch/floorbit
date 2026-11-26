import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Plugins from './Plugins'
import { PluginOverview } from './plugins/PluginOverview'

const plugin: PluginInfo = {
  id: 'http-check',
  name: 'HTTP check',
  version: '1.0.0',
  description: 'Checks web services.',
  trust: 'official',
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
    expect(screen.getByText('v1.0.0 · Official')).toBeInTheDocument()
    expect(within(screen.getByRole('list')).getByText('Off')).toBeInTheDocument()

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
      const { unmount } = renderWithApp(<PluginOverview plugin={{ ...plugin, ...extra }} />)
      expect(screen.getByText(text)).toBeInTheDocument()
      unmount()
    }
    renderWithApp(<PluginOverview plugin={plugin} />)
    expect(screen.queryByText(/schema/)).toBeNull()
  })

  it('says what each plugin does, and lists the LAN cache whose data is here without its plugin (#1435)', async () => {
    const receiving = { ...plugin, id: 'unifi', name: 'UniFi', enabled: true,
      uses: [{ id: 'agent', label: 'Agent' }], activity: { state: 'receiving' as const, values: { count: 2, total: 2 } } }
    const unset = { ...plugin, id: 'zabbix', name: 'Zabbix', enabled: true, activity: { state: 'not_configured' as const, values: {} } }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [receiving, unset], missing: [{ id: 'lancache', name: 'LAN cache', href: '/games' }] },
      'GET /api/settings/marketplace': { source: { url: '', name: '', generated: '', error: '' }, plugins: [] },
    }).fn)
    renderWithApp(<Plugins />)
    const card = (id: string) => document.querySelector(`[data-plugin="${id}"]`) as HTMLElement
    await screen.findByRole('heading', { name: 'UniFi' })
    expect(within(card('unifi')).getByText('Receiving')).toBeInTheDocument()
    expect(within(card('unifi')).getByText(/runs on the agent/)).toBeInTheDocument()
    expect(within(card('zabbix')).getByText('Not configured')).toBeInTheDocument()
    expect(within(card('lancache')).getByText('Not installed')).toBeInTheDocument()
    expect(within(card('lancache')).getByRole('link', { name: 'LAN cache' })).toHaveAttribute('href', '/games')
    fireEvent.click(within(card('lancache')).getByRole('button', { name: 'Install' }))
    expect(await screen.findByRole('tab', { name: 'Marketplace' })).toHaveAttribute('aria-selected', 'true')
  })

  it('lists only the Marketplace add-ons and points to Sources for the built-in ones (#1587)', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [plugin, { ...plugin, id: 'netbox', name: 'NetBox', trust: 'builtin' }] },
    }).fn)
    renderWithApp(<Plugins />)
    expect(await screen.findByRole('heading', { name: 'HTTP check' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'NetBox' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings › Sources' })).toHaveAttribute('href', '/settings/sources')
    expect(screen.getByRole('tab', { name: /Installed\s*1/ })).toBeInTheDocument()
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
      'GET /api/settings/marketplace': { source: { url: '', name: '', generated: '', error: '' }, plugins: [] },
    }).fn)
    renderWithApp(<Plugins />)
    fireEvent.click(await screen.findByRole('tab', { name: 'Marketplace' }))
    expect(await screen.findByRole('heading', { name: 'Marketplace', level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'HTTP check' })).toBeNull()
  })

  it('lists the installed plugins with a newer version under Updates, with their count on the tab', async () => {
    const market = (id: string, installed: string | null, update: string | null) => ({
      id, name: id, description: '', author: '', homepage: '', source: '', builtin: false, installed, previous: null,
      error: '', enabled: true, withdrawn: '', update, best: update ?? installed, listed: true, versions: [],
    })
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [plugin] },
      'GET /api/settings/marketplace': {
        source: { url: '', name: '', generated: '', error: '' },
        plugins: [market('lancache', '1.0.0', '1.1.0'), market('shelly', '1.0.0', null), market('extra', null, null)],
      },
    }).fn)
    renderWithApp(<Plugins />, '/settings/plugins?tab=updates')
    expect(await screen.findByRole('heading', { name: 'Updates', level: 2 })).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: /Updates\s*1/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('lancache')).toBeInTheDocument()
    expect(screen.queryByText('shelly')).toBeNull()
    expect(screen.queryByText('extra')).toBeNull()
  })
})
