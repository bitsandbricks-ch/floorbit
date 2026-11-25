import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { fakeFetch, renderWithApp } from '@/test/render'
import { contrast } from '@/colorContrast'
import Settings, { type SettingsAnswer } from './Settings'

afterEach(() => {
  vi.unstubAllGlobals()
  document.getElementById('fb-nav-data')?.remove()
})

const page = (route = '/settings') =>
  renderWithApp(<Routes><Route path="/settings/:section?" element={<Settings />} /></Routes>, route)

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const answer: SettingsAnswer = {
  sections: [
    { id: 'netbox', title: 'NetBox', description: 'Inventory.' },
    { id: 'general', title: 'Event', description: 'The event.' },
    { id: 'discord', title: 'Discord', description: 'Alerts to Discord.' },
    { id: 'cache', title: 'Caching', description: 'TTL.' },
  ],
  fields: [
    { key: 'netbox.url', section: 'netbox', label: 'NetBox URL', type: 'url', env: 'NETBOX_URL' },
    { key: 'event.name', section: 'general', label: 'Event name', type: 'text', env: 'EVENT_NAME' },
    { key: 'discord.url', section: 'discord', label: 'Webhook URL', type: 'url', env: 'DISCORD_URL' },
    { key: 'discord.token', section: 'discord', label: 'Bot token', type: 'secret', env: 'DISCORD_TOKEN' },
    { key: 'cache.ttl_arp', section: 'cache', label: 'ARP table TTL', type: 'int', env: 'CACHE_TTL_ARP', unit: 'seconds', min: 1, max: 86400 },
  ],
  values: {
    'netbox.url': { source: 'saved', value: 'https://netbox.example.com' },
    'event.name': { source: 'saved', value: 'Example LAN' },
    'discord.url': { source: 'default', value: '' },
    'discord.token': { source: 'env', is_set: true, env: 'DISCORD_TOKEN', env_set: true },
    'cache.ttl_arp': { source: 'default', value: 300 },
  },
  status: { netbox_enabled: true, librenms_enabled: false, redis: { connected: true, host: 'redis', port: 6379 } },
}

describe('Settings', () => {
  it('keeps changes across tabs and sections, and saves only the fields that changed', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer, 'PUT /api/settings': answer })
    vi.stubGlobal('fetch', api.fn)
    page()
    // General opens first, on its first section; NetBox is a plugin, so not here.
    fireEvent.click(await screen.findByRole('button', { name: 'Reset' }))
    expect(screen.getByRole('tab', { name: /General/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('link', { name: 'NetBox' })).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: /System/ }))
    expect(await screen.findByText('Not configured, no live status')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('link', { name: 'Caching' })[0])
    fireEvent.change(await screen.findByLabelText('ARP table TTL'), { target: { value: '600' } })
    expect(await screen.findByText('2 unsaved changes')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ 'cache.ttl_arp': 600, 'event.name': null })
    expect(await screen.findByText('Saved. Changes apply immediately.')).toBeInTheDocument()
  })

  it('does not save a value the server would refuse', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer }).fn)
    page('/settings/discord')
    expect(await screen.findByRole('tab', { name: /Alerts/ })).toHaveAttribute('aria-selected', 'true')
    fireEvent.change(await screen.findByLabelText('Webhook URL'), { target: { value: 'discord.example.com' } })
    expect(await screen.findByText('Not a valid value')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('says when a saved secret no longer opens, until a new one is typed', async () => {
    const broken = { ...answer, values: { ...answer.values, 'discord.token': { source: 'saved' as const, is_set: false, unreadable: true } } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': broken }).fn)
    page('/settings/discord')
    expect(await screen.findByText("Saved, but it doesn't open with the current secret key. Enter it again.")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Bot token'), { target: { value: 'token-example' } })
    await waitFor(() => expect(screen.queryByText(/doesn't open with the current secret key/)).toBeNull())
  })

  it('finds a field by its words or env var, and opens an old #sec- link on its section', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer }).fn)
    page('/settings#sec-discord')
    expect(await screen.findByLabelText('Webhook URL')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search settings'), { target: { value: 'cache_ttl' } })
    expect(await screen.findByLabelText('ARP table TTL')).toBeInTheDocument()
    expect(screen.queryByLabelText('Webhook URL')).toBeNull()
    expect(screen.getByText('1 setting matches')).toBeInTheDocument()
    // A plugin's field is found too, and leads to its plugin page.
    fireEvent.change(screen.getByLabelText('Search settings'), { target: { value: 'netbox_url' } })
    expect(await screen.findByRole('link', { name: 'NetBox' })).toHaveAttribute('href', '/settings/plugins/netbox')
    fireEvent.change(screen.getByLabelText('Search settings'), { target: { value: 'nothing like this' } })
    expect(await screen.findByText('No setting matches.')).toBeInTheDocument()
  })

  it('opens an admin page inside its tab, and shows people pages to an account that may not change settings', async () => {
    const people = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'lead', permissions: ['floorplan.view', 'accounts.manage'] } }
    const api = fakeFetch({
      'GET /api/auth/me': people,
      'GET /api/pages': { pages: [{ href: '/settings/users', id: 'users', label: 'Users' }, { href: '/settings/teams', id: 'teams', label: 'Roles and teams' }] },
      'GET /api/auth/users': { users: [], roles: [], teams: [], can_manage: true },
    })
    vi.stubGlobal('fetch', api.fn)
    page('/settings/teams')
    expect(await screen.findByRole('tab', { name: /People/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('tab', { name: /General/ })).toBeNull()
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute('href', '/settings/users')
    expect(await screen.findByRole('heading', { name: 'Roles and teams', level: 3 })).toBeInTheDocument()
    expect(api.calls.some((c) => c.path === '/api/settings')).toBe(false)
  })

  it('says where a value comes from only when it is not the default, with the env var in a tooltip', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer }).fn)
    page('/settings/discord')
    const fromEnv = await screen.findByText("Set by the server's environment")
    // The default webhook URL says nothing, and no env var name stands on the page.
    expect(screen.getAllByText(/^Set /)).toHaveLength(1)
    expect(screen.queryByText(/DISCORD_/)).toBeNull()
    fireEvent.mouseEnter(fromEnv.closest('span') as HTMLElement)
    expect(await screen.findByText(/environment variable DISCORD_TOKEN/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /General/ }))
    expect(await screen.findByText('Set here')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
  })

  it('keeps Tenants under System on one tenant, and gives it a tab only with several', async () => {
    const pages = { pages: [{ href: '/settings', id: 'settings', label: 'Settings' }, { href: '/settings/tenants', id: 'tenants', label: 'Tenants' }] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer, 'GET /api/pages': pages }).fn)
    const one = page('/settings/cache')
    expect(await screen.findByRole('tab', { name: /System/ })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('link', { name: 'Tenants' })).toHaveAttribute('href', '/settings/tenants')
    expect(screen.queryByRole('tab', { name: /Tenants/ })).toBeNull()
    one.unmount()

    const el = document.createElement('script')
    el.type = 'application/json'
    el.id = 'fb-nav-data'
    el.textContent = JSON.stringify({ tenants: true })
    document.body.append(el)
    page('/settings/cache')
    expect(await screen.findByRole('tab', { name: /Tenants/ })).toBeInTheDocument()
  })

  it('works out the contrast like the server', () => {
    expect(contrast('#ffffff', '#000000')).toBeCloseTo(21, 0)
  })
})

describe('Settings in German', () => {
  afterEach(async () => {
    const { default: i18n } = await import('@/i18n')
    await i18n.changeLanguage('en')
  })

  it('shows the integration and plugin settings in German too', async () => {
    const { default: i18n } = await import('@/i18n')
    await i18n.changeLanguage('de-CH')
    const german: SettingsAnswer = {
      ...answer,
      sections: [{ id: 'plugin-zabbix', title: 'Plugin: Zabbix', description: 'Live switch status from Zabbix.' }],
      fields: [{ key: 'plugin.zabbix.group', section: 'plugin-zabbix', label: 'Host group', type: 'text', env: null, help: 'Only hosts in this group are read.' }],
      values: { 'plugin.zabbix.group': { source: 'default', value: '' } },
    }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': german }).fn)
    page()
    fireEvent.change(await screen.findByLabelText('Einstellungen durchsuchen'), { target: { value: 'gruppe' } })
    expect(await screen.findByLabelText('Host-Gruppe')).toBeInTheDocument()
    expect(screen.getByText('Nur Hosts in dieser Gruppe werden gelesen.')).toBeInTheDocument()
    expect(screen.getByText(/Zustand, Verkehr und Fehler der Ports aus Zabbix/)).toBeInTheDocument()
  })

  it('folds the server-side values of a section under Advanced', async () => {
    const folded: SettingsAnswer = { ...answer, fields: answer.fields.map((f) => f.key === 'discord.token' ? { ...f, advanced: true } : f) }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': folded }).fn)
    page('/settings/discord')
    const toggle = await screen.findByRole('button', { name: /Advanced: 1 more/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByLabelText('Webhook URL')).toBeInTheDocument()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('Bot token')).toBeInTheDocument()
  })
})
