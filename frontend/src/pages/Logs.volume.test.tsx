import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LogsData, SyslogLine } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Logs from './Logs'
import type { LogVolumeData } from './logs/LogVolume'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const line = (id: number, over: Partial<SyslogLine> = {}): SyslogLine => ({
  id, ts: now + id, facility: 23, severity: 'info', host: null, program: null, message: `line ${id}`,
  sender: '192.0.2.9', device: 'sw-a-01', port: null, seat: null, ...over,
})
const data: LogsData = {
  lines: [line(2), line(1)],
  status: {
    enabled: true, listening: { port: 5514, tcp: false, bind: '0.0.0.0' }, error: null,
    counts: { received: 2, kept: 2, not_allowed: 0, rate_limited: 0 }, lines: 2, devices: ['sw-a-01'],
    retention_hours: 24, demo: false, last_id: 2, sources: ['syslog'], source: 'syslog',
  },
}
const volume: LogVolumeData = { since: now - 120, until: now, step: 60, buckets: [[now - 120, 0, 0], [now - 60, 5, 2]] }
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['seats.view'] } }

/** The window changes with the clock, so these answer every /api/logs and /api/logs/volume request. */
function stub() {
  const fake = fakeFetch({ 'GET /api/auth/me': me })
  const paths: string[] = []
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    paths.push(path)
    const body = path.startsWith('/api/logs/volume') ? volume : path.startsWith('/api/logs') ? data : undefined
    return body ? new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }) : fake.fn(input, init)
  })
  return paths
}

describe('Logs volume, pause and download (#1048)', () => {
  it('draws lines over time and narrows the list to a bar\'s time', async () => {
    const paths = stub()
    renderWithApp(<Logs />)
    const bar = await screen.findByRole('button', { name: /5 lines, 2 errors/ })
    expect(screen.getByRole('button', { name: /0 lines, 0 errors/ })).toBeDisabled()
    fireEvent.click(bar)
    await waitFor(() => expect(paths).toContain(`/api/logs?since=${now - 60}&until=${now}`))
    expect(screen.getByRole('button', { name: /^Time: / })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', `/api/logs/download?since=${now - 60}&until=${now}`)
  })

  it('pauses and resumes the live tail', async () => {
    stub()
    renderWithApp(<Logs />)
    fireEvent.click(await screen.findByRole('button', { name: 'Pause' }))
    expect(screen.getByRole('button', { name: 'Resume' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText('Live')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
    expect(screen.getByText('Live')).toBeInTheDocument()
  })

  it('asks for the last hour when that time is picked', async () => {
    const paths = stub()
    renderWithApp(<Logs />, '/logs?range=1h')
    await screen.findByText('line 2')
    expect(paths.some((p) => /^\/api\/logs\?since=\d+$/.test(p))).toBe(true)
    expect(screen.getByRole('link', { name: 'Download' }).getAttribute('href')).toMatch(/^\/api\/logs\/download\?since=\d+$/)
  })
})
