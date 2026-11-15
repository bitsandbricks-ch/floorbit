import { fireEvent, screen, within } from '@testing-library/react'
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

  it('shows the bandwidth forecast, how it was made and a warning', async () => {
    const t0 = 1_800_000_000
    const points = Array.from({ length: 12 }, (_, k) => ({ t: t0 + k * 3600, bps: (k === 2 ? 9 : 4) * 1e9, low: 3e9,
      high: 9.5e9, basis: 'profile' as const, pct: k === 2 ? 90 : 40 }))
    const forecast = { ready: true, history_hours: 40, min_hours: 6, capacity_bps: 10e9, warn_pct: 80, lead_hours: 3,
      points, alert: { t: t0 + 7200, bps: 9e9, pct: 90 }, level: 1.2, days: 2, peak: points[2] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/stats': stats(), 'GET /api/forecast': forecast }).fn)
    renderWithApp(<Stats />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Expected at 90 % of the line')
    expect(screen.getByRole('img', { name: /Bandwidth forecast: busiest expected 9.0 Gbps/ })).toBeInTheDocument()
    expect(screen.getByText(/from 2 days of this event\. The last 3 hours ran 20 % busier/)).toBeInTheDocument()
  })

  it('compares today with yesterday and this event with the last one', async () => {
    const side = (avg: number, incidents: number) => ({ peak_bps: avg * 2, avg_bps: avg, bytes_moved: avg * 450, online_max: 80,
      hours: 10, incidents, outages: 1 })
    const series = Array.from({ length: 24 }, (_, hour) => ({ hour, now_avg_bps: 2e9, then_avg_bps: 1e9, now_online: 80, then_online: 70 }))
    const compare = { day: { now: side(2e9, 3), then: side(1e9, 2), series, has_then: true },
      event: { name: 'Example LAN 2025', id: 'x', then_start: 1, elapsed_s: 36000, now: side(2e9, 3), then: side(4e9, 6), series } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/stats': stats(), 'GET /api/stats/compare': compare }).fn)
    renderWithApp(<Stats />)
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('row', { name: /Average bandwidth 2.0 Gbps 1.0 Gbps \+100 %/ })).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /Incidents 3 2 \+50 %/ })).toBeInTheDocument()
    expect(screen.getByText('Today so far, and yesterday until the same time.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('This event and Example LAN 2025'))
    expect(screen.getByText('The first 10 hours of this event, and of Example LAN 2025.')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByRole('row', { name: /Average bandwidth 2.0 Gbps 4.0 Gbps -50 %/ })).toBeInTheDocument()
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
