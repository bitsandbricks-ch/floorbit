import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SpeedtestSummary } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Speedtests from './Speedtests'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: false }
const at = 1_800_000_000
const data: SpeedtestSummary = {
  hours: 12,
  hall: { tests: 5, down_mbps: 900, up_mbps: 850, ping_ms: 1.2 },
  switches: [
    { id: 's2', name: 'sw-b-01', tests: 2, down_mbps: 95.5, up_mbps: 90, ping_ms: 4, slow: true,
      seats: [{ seat: 'B-1', down_mbps: 91, up_mbps: 88, ping_ms: 4, at }, { seat: 'B-2', down_mbps: 100, up_mbps: 92, ping_ms: 4, at }] },
    { id: 's1', name: 'sw-a-01', tests: 2, down_mbps: 930, up_mbps: 880, ping_ms: 1, slow: false,
      seats: [{ seat: 'A-1', down_mbps: 920, up_mbps: 870, ping_ms: 1, at }, { seat: 'A-2', down_mbps: 940, up_mbps: 890, ping_ms: 1, at }] },
  ],
  unknown: [{ seat: 'C-9', down_mbps: 910, up_mbps: null, ping_ms: 2, at }],
}

describe('Speedtests', () => {
  it('shows the hall and one row per switch, the slow one marked', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/speedtests/summary': data }).fn)
    renderWithApp(<Speedtests />)
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(within(rows[0]).getByRole('link', { name: 'sw-b-01' })).toHaveAttribute('href', '/plan?switch=sw-b-01')
    expect(within(rows[0]).getByText('Slower than the hall')).toBeInTheDocument()
    expect(within(rows[0]).getByText('95.5 Mbit/s')).toBeInTheDocument()
    expect(within(rows[0]).getByRole('link', { name: 'B-1' })).toHaveAttribute('href', '/plan?seat=B-1')
    expect(within(rows[1]).queryByText('Slower than the hall')).not.toBeInTheDocument()
    expect(screen.getByText('900 Mbit/s')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Seats with no known switch' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'C-9' })).toBeInTheDocument()
  })
  it('says how to get results when there are none', async () => {
    const empty: SpeedtestSummary = { hours: 12, hall: { tests: 0, down_mbps: null, up_mbps: null, ping_ms: null }, switches: [], unknown: [] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/speedtests/summary': empty }).fn)
    renderWithApp(<Speedtests />)
    expect(await screen.findByText(/No speed tests in the last 12 hours/)).toBeInTheDocument()
  })
})
