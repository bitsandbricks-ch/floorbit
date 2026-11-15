import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SyslogLine, LogsData, LogStatus } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Logs from './Logs'

afterEach(() => vi.unstubAllGlobals())

const now = 1_800_000_000
const line = (id: number, over: Partial<SyslogLine> = {}): SyslogLine => ({
  id, ts: now + id, facility: 23, severity: 'info', host: null, program: null, message: `line ${id}`,
  sender: '192.0.2.9', device: 'sw-a-01', port: null, seat: null, ...over,
})
const status = (over: Partial<LogStatus> = {}): LogStatus => ({
  enabled: true, listening: { port: 5514, tcp: false, bind: '0.0.0.0' }, error: null,
  counts: { received: 12, kept: 10, not_allowed: 2, rate_limited: 0 }, lines: 2, devices: ['dhcp-01', 'sw-a-01'],
  retention_hours: 24, demo: false, last_id: 2, sources: ['syslog'], source: 'syslog', ...over,
})
const logs = (lines: SyslogLine[], over: Partial<LogStatus> = {}): LogsData => ({ lines, status: status(over) })
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['seats.view'] } }

describe('Logs', () => {
  it('shows the lines with their device, port and seat', async () => {
    const down = line(2, { severity: 'err', program: '%LINK-3-UPDOWN', message: 'Interface Gi1/0/4, changed state to down',
      port: 'gi1/0/4', seat: 'A-4' })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs([down, line(1)]) }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText('Interface Gi1/0/4, changed state to down')).toBeInTheDocument()
    expect(screen.getByText('Error')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'seat A-4' })).toHaveAttribute('href', '/?seat=A-4')
    expect(screen.getByText('Listening on UDP 5514')).toBeInTheDocument()
    expect(screen.getByText(/2 from senders not allowed/)).toBeInTheDocument()
  })

  it('filters by device when one is clicked', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/logs': logs([line(2, { device: 'dhcp-01' }), line(1)]),
      'GET /api/logs?device=dhcp-01': logs([line(2, { device: 'dhcp-01', message: 'only dhcp' })]),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />)
    fireEvent.click(await screen.findByRole('button', { name: 'dhcp-01' }))
    expect(await screen.findByText('only dhcp', {}, { timeout: 2000 })).toBeInTheDocument()
    expect(screen.queryByText('line 1')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
  })

  it('pages back to older lines', async () => {
    const page = Array.from({ length: 200 }, (_, i) => line(400 - i))
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/logs': logs(page),
      'GET /api/logs?before=201': logs([line(200, { message: 'an older one' })]),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />)
    fireEvent.click(await screen.findByRole('button', { name: 'Older lines' }))
    expect(await screen.findByText('an older one')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Older lines' })).not.toBeInTheDocument())
  })

  it('opens filtered from a link', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs?seat=A-4': logs([line(5, { seat: 'A-4', message: 'on A-4' })]) })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />, '/logs?seat=A-4')
    expect(await screen.findByText('on A-4')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A-4')).toBeInTheDocument()
  })

  it('switches to Floorbit\'s own log and the audit log', async () => {
    const all = { sources: ['syslog', 'app', 'audit'] as const }
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/logs': logs([line(1)], { sources: [...all.sources] }),
      'GET /api/logs?source=app': logs([line(9, { device: 'Floorbit', program: 'syslog', message: 'could not prune' })],
        { sources: [...all.sources], source: 'app' }),
      'GET /api/logs?source=audit': logs([line(4, { device: 'kim', program: 'floor plan', message: 'Changed switch sw-a-01' })],
        { sources: [...all.sources], source: 'audit' }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />)
    fireEvent.click(await screen.findByText('Floorbit'))
    expect(await screen.findByText('could not prune')).toBeInTheDocument()
    expect(screen.queryByLabelText('Seat')).not.toBeInTheDocument()
    expect(screen.queryByText('Listening on UDP 5514')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Audit log'))
    expect(await screen.findByText('Changed switch sw-a-01')).toBeInTheDocument()
  })

  it('searches Loki with LogQL when it is sent', async () => {
    const sources = ['syslog', 'plugin:loki'] as const
    const stores = [{ id: 'loki', name: 'Grafana Loki', sent: 1200, error: null }]
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/logs': logs([line(1)], { sources: [...sources], stores }),
      'GET /api/logs?source=plugin%3Aloki&hours=24': logs([line(1_800_000_000_000_000, { message: 'from loki' })],
        { sources: [...sources], stores, source: 'plugin:loki' }),
      'GET /api/logs?q=%7Bdevice%3D%22sw-a-01%22%7D&source=plugin%3Aloki&hours=24': logs([], {
        sources: [...sources], stores, source: 'plugin:loki', query_error: "Loki can't read that query: parse error" }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText(/Grafana Loki: 1,200 lines sent/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Grafana Loki'))
    expect(await screen.findByText('from loki')).toBeInTheDocument()
    const box = screen.getByLabelText('LogQL query')
    fireEvent.change(box, { target: { value: '{device="sw-a-01"}' } })
    expect(fake.calls.filter((c) => c.path.includes('sw-a-01'))).toHaveLength(0)   // not while typing
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(await screen.findByText(/parse error/)).toBeInTheDocument()
  })

  it('explains how to turn the receiver on', async () => {
    const off = logs([], { enabled: false, listening: null, lines: 0, devices: [] })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': off }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText(/The syslog receiver is off/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'docs/syslog.md' })).toBeInTheDocument()
  })
})
