import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PluginInfo } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Sources from './Sources'

const base: PluginInfo = {
  id: 'netbox', name: 'NetBox', version: '1.0.0', description: '', trust: 'builtin', author: '', homepage: '',
  uses: [], enabled: true, error: null, settings_section: null, actions: [], widgets: [], endpoints: [], hooks: [], has_test: false,
}

afterEach(() => vi.unstubAllGlobals())

describe('Settings › Sources', () => {
  it('lists the built-in sources, then what every agent does, without the add-ons (#1587)', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false, user: null },
      'GET /api/settings/plugins': { plugins: [
        base,
        { ...base, id: 'telemetry', name: 'Telemetry', agent: { actions: [], calls: [], sends: [] } },
        { ...base, id: 'lancache', name: 'LAN cache', trust: 'official' },
      ] },
    }).fn)
    renderWithApp(<Sources />)
    const hosted = await screen.findByRole('region', { name: 'What Floorbit asks' })
    expect(within(hosted).getByRole('link', { name: 'NetBox' })).toHaveAttribute('href', '/settings/plugins/netbox')
    const agent = screen.getByRole('region', { name: 'What every agent does' })
    expect(within(agent).getByRole('heading', { name: 'Telemetry' })).toBeInTheDocument()
    expect(screen.queryByText('LAN cache')).not.toBeInTheDocument()
  })
})
