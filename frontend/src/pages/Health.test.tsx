import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HealthCheck, HealthWall } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Health from './Health'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const check = (c: Partial<HealthCheck> & Pick<HealthCheck, 'id' | 'name' | 'kind' | 'status'>): HealthCheck => ({
  summary: '', metrics: [], link: '', plugin: 'demo', plugin_name: 'Demo data', since: now - 90, ...c,
})
const wall: HealthWall = {
  checks: [
    check({ id: 'demo:dhcp', name: 'DHCP players', kind: 'dhcp', status: 'warn', summary: '18 of 100 leases left',
      metrics: [{ label: 'Leases left', value: 18, unit: '', tone: '' }] }),
    check({ id: 'demo:cache', name: 'LAN cache', kind: 'cache', status: 'up', summary: '80 % hit rate' }),
    check({ id: 'demo:game-3', name: 'Game server 3', kind: 'game', status: 'down', summary: 'Not answering' }),
  ],
  counts: { up: 1, warn: 1, down: 1, unknown: 0 },
  last_poll: now - 5,
  interval: 30,
  plugins: 1,
}
const me = (permissions: string[]) => ({
  enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions },
})

describe('Health wall', () => {
  it('groups services by kind and says each state in words', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me(['floorplan.view']), 'GET /api/health': wall }).fn)
    renderWithApp(<Health />)
    const dhcp = await screen.findByRole('region', { name: 'DHCP' })
    const tile = within(dhcp).getByRole('article', { name: 'DHCP players: Degraded' })
    expect(within(tile).getByText('18 of 100 leases left')).toBeInTheDocument()
    expect(within(tile).getByText('Leases left')).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Game server 3: Down' })).toBeInTheDocument()
    expect(screen.getByText('1 down')).toBeInTheDocument()
    // Only accounts that may run plugins can ask for a check now.
    expect(screen.queryByRole('button', { name: 'Check now' })).not.toBeInTheDocument()
  })

  it('checks now for accounts that may run plugins', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me(['floorplan.view', 'plugins.run']),
      'GET /api/health': wall,
      'POST /api/health/check': { ...wall, checks: [check({ id: 'demo:cache', name: 'LAN cache', kind: 'cache', status: 'up' })],
        counts: { up: 1, warn: 0, down: 0, unknown: 0 } },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Health />)
    fireEvent.click(await screen.findByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(screen.queryByText('Game server 3')).not.toBeInTheDocument())
  })

  it('says how to get services onto the wall', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me(['floorplan.view']),
      'GET /api/health': { checks: [], counts: { up: 0, warn: 0, down: 0, unknown: 0 }, last_poll: null, interval: 30, plugins: 0 },
    }).fn)
    renderWithApp(<Health />)
    expect(await screen.findByText(/No health plugin is on yet/)).toBeInTheDocument()
  })
})
