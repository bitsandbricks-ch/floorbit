import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { PluginPanels } from './PluginPanels'

afterEach(() => vi.unstubAllGlobals())

const panel = (id: string, label: string) => ({
  plugin: 'hallthing', plugin_name: 'Hall thing', icon: 'chart', id, label, refresh: 60, url: `/api/plugins/hallthing/panels/${id}`,
})

describe('PluginPanels', () => {
  it('shows each box with its own result, and a broken one only as its own error', async () => {
    const api = fakeFetch({
      'GET /api/plugins/panels?on=seat': { panels: [panel('load', 'Seat load'), panel('broken', 'Broken')] },
      'GET /api/plugins/hallthing/panels/load?target=A-12': { type: 'stat', value: 42, unit: 'Mbit/s', tone: '', label: 'Seat load', sub: 'last minute', link: '' },
      'GET /api/plugins/hallthing/panels/broken?target=A-12': () => ({ status: 502, body: { error: 'Hall thing did not answer within 10 s' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<PluginPanels on="seat" target="A-12" />)
    const load = await screen.findByRole('region', { name: 'Seat load' })
    expect(await within(load).findByText('last minute')).toBeInTheDocument()
    expect(within(load).getByText('Hall thing')).toBeInTheDocument()
    const broken = screen.getByRole('region', { name: 'Broken' })
    expect(await within(broken).findByRole('alert')).toHaveTextContent('did not answer')
  })

  it('draws nothing when no plugin has a panel here', async () => {
    const api = fakeFetch({ 'GET /api/plugins/panels?on=switch': { panels: [] } })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<PluginPanels on="switch" target="sw-1" />)
    await vi.waitFor(() => expect(api.calls.length).toBeGreaterThan(0))
    expect(container.querySelector('section')).toBeNull()
  })
})
