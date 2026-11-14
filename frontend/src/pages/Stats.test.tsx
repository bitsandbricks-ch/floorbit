import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StatsData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Stats from './Stats'
import { bps } from './stats/format'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const M = 1e6
const stats = (over: Partial<StatsData> = {}): StatsData => ({
  monitoring: true, interval: 120, last_poll: now,
  now: { t: now, down: 1800 * M, up: 240 * M, online: 84, ports_up: 96, ports_down: 12, ports_errors: 1 },
  hour: { avg_bps: 1500 * M, peak_bps: 2100 * M, peak_at: now - 600, online_max: 85, samples: 30 },
  day: { avg_bps: 900 * M, peak_bps: 2600 * M, peak_at: now - 7200, online_max: 88, samples: 720 },
  peak: { bps: 2600 * M, at: now - 7200 },
  series: [0, 1, 2].map((i) => ({ t: now - (2 - i) * 120, down: (1000 + i * 100) * M, up: 100 * M, online: 80 + i })),
  uplinks: [{ switch_id: 's1', switch: 'sw-a-01', port: 'Te1/1/1', bps: 8_500 * M, speed_bps: 10_000 * M, utilization: 0.85 }],
  top: [{ seat: 'A-12', switch_id: 's1', switch: 'sw-a-01', port: 'Gi1/0/12', download_bps: 300 * M, upload_bps: 20 * M, bps: 320 * M, nick: 'player-one' }],
  ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'admin', permissions: ['settings.manage'] } }

describe('Stats', () => {
  it('formats bandwidth', () => {
    expect(bps(2_600_000_000)).toBe('2.6 Gbps')
    expect(bps(320_000_000)).toBe('320 Mbps')
    expect(bps(1_500_000)).toBe('1.5 Mbps')
    expect(bps(0)).toBe('0 bps')
  })

  it('shows bandwidth, peaks, uplinks and top talkers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/stats': stats() }).fn)
    renderWithApp(<Stats />)
    const row = await screen.findByLabelText('Bandwidth')
    expect(within(row).getByText('2.0 Gbps')).toBeInTheDocument()   // 1.8 down + 0.24 up
    expect(within(row).getAllByText('2.6 Gbps')).toHaveLength(2)   // the day's and the event's peak
    expect(within(row).getByText('84')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'sw-a-01 Te1/1/1' })).toHaveAttribute('aria-valuenow', '85')
    expect(screen.getByText('Seat A-12')).toBeInTheDocument()
    expect(screen.getByText(/player-one/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Traffic over time' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset peak' })).toBeInTheDocument()
  })

  it('says it is collecting before the first read', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/stats': stats({ now: null, hour: null, day: null, peak: null, series: [] }) }).fn)
    renderWithApp(<Stats />)
    expect(await screen.findByText(/Collecting/)).toBeInTheDocument()
  })

  it('asks the screen version without nicks', async () => {
    window.history.pushState({}, '', '/stats?screen=1')
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/stats': stats({ top: [{ ...stats().top[0], nick: undefined }] }) })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Stats />)
    expect(await screen.findByRole('heading', { name: 'Stats', level: 1 })).toBeInTheDocument()
    expect(fake.calls.some((c) => c.path === '/api/stats?screen=1')).toBe(true)
    expect(screen.queryByRole('button', { name: 'Reset peak' })).not.toBeInTheDocument()
    window.history.pushState({}, '', '/')
  })
})
