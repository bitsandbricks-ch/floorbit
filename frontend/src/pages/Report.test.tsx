import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EventReport } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Report from './Report'
import { duration, pdfUrl } from './report/format'

afterEach(() => vi.unstubAllGlobals())

const t0 = 1_800_000_000
const viewer = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: ['floorplan.view'] } }
const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const data: EventReport = {
  event_name: 'Example LAN', start: t0, end: t0 + 7200, generated: t0 + 7300, people: false, may_add_people: false,
  seats: 96, online_max: 80, checked_in_max: 70, peak: { bps: 4.2e9, at: t0 + 3000 }, bytes_moved: 2.5e12,
  hours: [
    { t: t0, online_max: 40, checked_in: 30, peak_bps: 2e9, avg_bps: 1e9 },
    { t: t0 + 3600, online_max: 80, checked_in: 70, peak_bps: 4.2e9, avg_bps: 3e9 },
  ],
  outages: [{ switch: 'sw-c-02', times: 2, down_s: 1680, longest_s: 1260, still_down: false }],
  problem_ports: [{ switch: 'sw-b-01', port: 'Gi1/0/7', seat: 'B-7', count: 12, kinds: { flapping: 9, errors: 3 }, last: t0 }],
  incidents: {
    total: 1, fixed: 1, open: 0, from_seats: 1, median_fix_s: 900,
    items: [{ title: 'No internet at the seat', seat: 'B-7', switch: null, circuit: null, team: 'infra', source: 'helpdesk',
      reports: 2, start: t0 + 100, end: t0 + 1000, status: 'fixed' }],
  },
}

describe('report helpers', () => {
  it('formats durations and the PDF link', () => {
    expect(duration(45)).toBe('45 s')
    expect(duration(1680)).toBe('28 min')
    expect(duration(3900)).toBe('1 h 05 min')
    expect(pdfUrl('de-CH', false, -60)).toBe('/api/report.pdf?lang=de&tz=-60')
    expect(pdfUrl('en', true, 0)).toBe('/api/report.pdf?lang=en&tz=0&people=1')
  })
})

describe('Report', () => {
  it('shows the figures and tables without people data for a viewer', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/report': data }).fn)
    renderWithApp(<Report />)
    expect(await screen.findByText('4.2 Gbps')).toBeInTheDocument()
    expect(screen.getByText('2.5 TB')).toBeInTheDocument()
    expect(screen.getByText('sw-c-02')).toBeInTheDocument()
    expect(screen.getByText('flapping 9×, errors 3×')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download PDF/ })).toHaveAttribute('href', expect.stringContaining('/api/report.pdf?lang=en'))
    expect(screen.queryByRole('switch', { name: /nicks and IPs/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start a new event' })).not.toBeInTheDocument()
  })

  it('lets an admin add nicks and IPs', async () => {
    const withPeople = { ...data, people: true, may_add_people: true,
      problem_ports: [{ ...data.problem_ports[0], nick: 'player-seven', ip: '198.51.100.7' }] }
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/report': { ...data, may_add_people: true }, 'GET /api/report?people=1': withPeople,
    }).fn)
    renderWithApp(<Report />)
    fireEvent.click(await screen.findByRole('switch', { name: /nicks and IPs/ }))
    expect(await screen.findByText('player-seven')).toBeInTheDocument()
    expect(screen.getByText(/Handle it as personal data/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Download PDF/ })).toHaveAttribute('href', expect.stringContaining('people=1'))
  })
})
