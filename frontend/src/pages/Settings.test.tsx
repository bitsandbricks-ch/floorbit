import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { contrast } from '@/colorContrast'
import Settings, { type SettingsAnswer } from './Settings'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const answer: SettingsAnswer = {
  sections: [
    { id: 'netbox', title: 'NetBox', description: 'Inventory.' },
    { id: 'cache', title: 'Caching', description: 'TTL.' },
  ],
  fields: [
    { key: 'netbox.url', section: 'netbox', label: 'URL', type: 'url', env: 'NETBOX_URL' },
    { key: 'netbox.token', section: 'netbox', label: 'API token', type: 'secret', env: 'NETBOX_TOKEN' },
    { key: 'cache.ttl_arp', section: 'cache', label: 'ARP table TTL', type: 'int', env: 'CACHE_TTL_ARP', unit: 'seconds', min: 1, max: 86400 },
  ],
  values: {
    'netbox.url': { source: 'saved', value: 'https://netbox.example.com' },
    'netbox.token': { source: 'env', is_set: true, env: 'NETBOX_TOKEN', env_set: true },
    'cache.ttl_arp': { source: 'default', value: 300 },
  },
  status: { netbox_enabled: true, librenms_enabled: false, redis: { connected: true, host: 'redis', port: 6379 } },
}

describe('Settings', () => {
  it('saves only the fields that changed, and resets a saved one to its default', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/settings': answer, 'PUT /api/settings': answer,
      'POST /api/settings/test/netbox': { ok: true, message: 'Connected, 12 switches' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Settings />)
    expect(await screen.findByText('Not configured, no live status')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download backup' })).toHaveAttribute('href', '/api/settings/backup')

    fireEvent.change(screen.getByLabelText('ARP table TTL'), { target: { value: '600' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(await screen.findByText('2 unsaved changes')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    expect(await screen.findByText('Connected, 12 switches')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PUT')).toBe(true))
    const put = api.calls.find((c) => c.method === 'PUT')
    expect(put?.body).toEqual({ 'cache.ttl_arp': 600, 'netbox.url': null })
    expect(await screen.findByText('Saved. Changes apply immediately.')).toBeInTheDocument()
  })

  it('does not save a value the server would refuse', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/settings': answer }).fn)
    renderWithApp(<Settings />)
    fireEvent.change(await screen.findByLabelText('URL'), { target: { value: 'netbox.example.com' } })
    expect(await screen.findByText('Not a valid value')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
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
    renderWithApp(<Settings />)
    expect(await screen.findByLabelText('Host-Gruppe')).toBeInTheDocument()
    expect(screen.getByText('Nur Hosts in dieser Gruppe werden gelesen.')).toBeInTheDocument()
    expect(screen.getByText(/Zustand, Verkehr und Fehler der Ports aus Zabbix/)).toBeInTheDocument()
  })
})
