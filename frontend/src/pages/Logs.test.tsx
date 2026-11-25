import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SyslogLine, LogsData, LogStatus } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Logs from './Logs'
import { useLocation } from 'react-router-dom'

function Where() {
  return <output data-testid="where">{useLocation().search}</output>
}

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
    expect(screen.getByRole('link', { name: 'seat A-4' })).toHaveAttribute('href', '/plan?seat=A-4')
    expect(screen.getByText('Listening on UDP 5514')).toBeInTheDocument()
    expect(screen.getByText(/2 from senders not allowed/)).toBeInTheDocument()
  })

  it('says which local agent sends the syslog', async () => {
    const relayed = [{ agent: 'Hall 2', at: now, lines: 40, dropped: 3, recent: true }]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs([line(1)], { enabled: false, listening: null, relayed }) }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText('Through the local agent Hall 2 · 3 dropped on the agent')).toBeInTheDocument()
    expect(screen.queryByText(/The syslog receiver is off/)).not.toBeInTheDocument()
  })

  it('says how many DHCP leases the syslog gave', async () => {
    const leases = { granted: 1200, released: 3, last_at: now }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs([line(1)], { leases }) }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText(/1,200 DHCP leases read for IP to MAC/)).toBeInTheDocument()
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
    await screen.findByText('line 400')
    // Only on the last page, where the lines run out.
    expect(screen.queryByRole('button', { name: 'Older lines' })).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: '4' }).at(-1)!)
    fireEvent.click(await screen.findByRole('button', { name: 'Older lines' }))
    expect(await screen.findByText('an older one')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Older lines' })).not.toBeInTheDocument())
  })

  it('shows 50 lines a page, sorts by level and holds the tail meanwhile (issue #1206)', async () => {
    const page = Array.from({ length: 120 }, (_, i) => line(120 - i, i === 100 ? { severity: 'emerg', message: 'the worst one' } : {}))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs(page) }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText('line 120')).toBeInTheDocument()
    expect(screen.getByText('120 lines loaded')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(51)   // the header and 50 lines
    expect(screen.queryByText('the worst one')).not.toBeInTheDocument()
    // The column's sort button, not the Level filter ("Level: All").
    fireEvent.click(screen.getByRole('button', { name: /^Level(?!:)/ }))
    expect(await screen.findByText('the worst one')).toBeInTheDocument()
    expect(screen.getByText('Live, paused')).toBeInTheDocument()
  })

  it('keeps the filters in the address (issue #1206)', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs([line(1)]),
      'GET /api/logs?q=uplink': logs([line(2, { message: 'uplink flapped' })]) })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<><Logs /><Where /></>)
    // Typing waits 300 ms before it asks (useSettled); a busy CI runner needs more than 2 s for that and the render.
    fireEvent.change(await screen.findByPlaceholderText('Words that all have to be in the line'), { target: { value: 'uplink' } })
    expect(await screen.findByText('uplink flapped', {}, { timeout: 4000 })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('?q=uplink'))
  })

  it('opens filtered from a link', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs?seat=A-4': logs([line(5, { seat: 'A-4', message: 'on A-4' })]),
      'GET /api/options/seats': { options: [{ value: 'A-4', label: 'A-4' }] } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />, '/logs?seat=A-4')
    expect(await screen.findByText('on A-4')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /^Seat: A-4/ })).toBeInTheDocument()
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

  it('shows only the new answer when lines sent in one go share their time (VictoriaLogs)', async () => {
    const sources = ['syslog', 'plugin:victorialogs'] as const
    const stores = [{ id: 'victorialogs', name: 'VictoriaLogs', sent: 3, error: null }]
    const at = 1_800_000_000_000_000
    const opts = { sources: [...sources], stores, source: 'plugin:victorialogs' as const }
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/logs': logs([line(1)], { sources: [...sources], stores }),
      'GET /api/logs?source=plugin%3Avictorialogs&hours=24': logs([
        line(at + 1, { device: 'sw-b-01', message: 'from b' }), line(at, { device: 'sw-a-01', message: 'from a' }), line(at, { device: 'sw-c-02', message: 'from c' }),
      ], opts),
      'GET /api/logs?q=device%3Asw-c-02&source=plugin%3Avictorialogs&hours=24': logs([line(at, { device: 'sw-c-02', message: 'only c' })], opts),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Logs />)
    fireEvent.click(await screen.findByText('VictoriaLogs'))
    expect(await screen.findByText('from a')).toBeInTheDocument()
    const box = screen.getByLabelText('LogsQL query')
    fireEvent.change(box, { target: { value: 'device:sw-c-02' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(await screen.findByText('only c')).toBeInTheDocument()
    expect(screen.queryByText('from a')).not.toBeInTheDocument()
  })

  it('explains how to turn the receiver on', async () => {
    const off = logs([], { enabled: false, listening: null, lines: 0, devices: [] })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': off }).fn)
    renderWithApp(<Logs />)
    expect(await screen.findByText(/The syslog receiver is off/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'docs/syslog.md' })).toBeInTheDocument()
  })

  it('shows port and seat in columns of their own and one line a message until the row is clicked (#1048)', async () => {
    const long = line(3, { message: 'a long message '.repeat(20).trim(), port: 'gi1/0/7', seat: 'B-2' })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/logs': logs([long]) }).fn)
    renderWithApp(<Logs />)
    const text = await screen.findByText(long.message)
    expect(screen.getByRole('columnheader', { name: /Port/ })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Seat/ })).toBeInTheDocument()
    const box = text.closest('[data-line-clamp]')
    expect(box).not.toBeNull()
    fireEvent.click(text)
    await waitFor(() => expect(screen.getByText(long.message).closest('[data-line-clamp]')).toBeNull())
  })
})

