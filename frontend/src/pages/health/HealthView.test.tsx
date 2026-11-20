import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HealthCheck, HealthWall } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import HealthView from './HealthView'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const scope = (extra: Partial<HealthCheck>): HealthCheck => ({
  id: 'dhcp:scope', name: 'DHCP players', kind: 'dhcp', status: 'up', summary: '40 of 120 addresses free', metrics: [],
  link: '', plugin: 'dhcp', plugin_name: 'DHCP', since: now - 60, ...extra,
})
const wall = (checks: HealthCheck[]): HealthWall => ({
  checks, counts: { up: 0, warn: checks.length, down: 0, unknown: 0 }, last_poll: now, interval: 30, plugins: 1,
} as HealthWall)

describe('HealthView', () => {
  it('says when a filling DHCP scope runs full (#1061)', async () => {
    const fc = { used: 80, total: 120, pct: 67, rate_per_min: 1, full_in_min: 40, level: 'warn' as const, raised: true }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: false },
      'GET /api/health': wall([scope({ status: 'warn', forecast: fc }), scope({ id: 'dhcp:staff', name: 'DHCP staff',
        forecast: { ...fc, full_in_min: 900, raised: false } })]),
    }).fn)
    renderWithApp(<HealthView expanded />, '/health')
    expect(await screen.findByText('Full in about 40 minutes at 1 a minute')).toHaveClass('fb-tone-warn')
    expect(screen.queryByText(/Full in about 900/)).not.toBeInTheDocument()     // too far out to matter
  })
})
