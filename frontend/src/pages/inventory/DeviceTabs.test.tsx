import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DeviceInterface } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DeviceGraphs } from './DeviceGraphs'
import { DeviceLogs } from './DeviceLogs'

afterEach(() => vi.unstubAllGlobals())

const crew = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['seats.view'] } }
const status = { listening: null, demo: true, lines: 2, retention_hours: 24, counts: { not_allowed: 0, rate_limited: 0 } }
const line = (id: number, message: string) => ({ id, ts: 1_700_000_000 + id, facility: 23, severity: 'err', host: 'sw-a-01',
  program: 'LINK', message, sender: '192.0.2.10', device: 'sw-a-01', port: 'Gi1/0/7', seat: null })

describe('Logs tab', () => {
  it('shows the device\'s lines and narrows them by text', async () => {
    const f = fakeFetch({ 'GET /api/auth/me': crew,
      'GET /api/logs?device=sw-a-01&limit=200': { lines: [line(2, 'Interface Gi1/0/7 changed to down'), line(1, 'err-disable')], status },
      'GET /api/logs?device=sw-a-01&limit=200&q=disable': { lines: [line(1, 'err-disable')], status } })
    vi.stubGlobal('fetch', f.fn)
    renderWithApp(<DeviceLogs name="sw-a-01" />)
    expect(await screen.findByText('Interface Gi1/0/7 changed to down')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open in Logs/ })).toHaveAttribute('href', '/logs?device=sw-a-01')
    fireEvent.change(screen.getByRole('textbox', { name: 'Search the lines' }), { target: { value: 'disable' } })
    await waitFor(() => expect(screen.queryByText('Interface Gi1/0/7 changed to down')).not.toBeInTheDocument())
    expect(screen.getByText('err-disable')).toBeInTheDocument()
  })

  it('says where the lines come from when there are none', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': crew,
      'GET /api/logs?device=sw-a-01&limit=200': { lines: [], status } }).fn)
    renderWithApp(<DeviceLogs name="sw-a-01" />)
    expect(await screen.findByText('No log lines from this device')).toBeInTheDocument()
    expect(screen.getByText(/syslog lines whose sender is sw-a-01/)).toBeInTheDocument()
  })
})

const iface = (name: string) => ({ id: name, name, type: 'copper', hidden: false }) as unknown as DeviceInterface
const pts = (vs: number[]) => vs.map((v, i) => [1_700_000_000 + i * 60, v])

describe('Graphs tab', () => {
  it('draws the device\'s load and one port\'s traffic, leaving out what was never stored', async () => {
    const empty = { points: [] }
    const f = fakeFetch({ 'GET /api/auth/me': crew,
      'GET /api/telemetry/series?device=sw-a-01&metric=cpu&hours=6': { points: pts([10, 30, 20]) },
      'GET /api/telemetry/series?device=sw-a-01&metric=mem&hours=6': empty,
      'GET /api/telemetry/series?device=sw-a-01&metric=up&hours=6': { points: pts([1, 1, 1]) },
      'GET /api/telemetry/series?device=sw-a-01&metric=in_bps&hours=6&port=Gi1%2F0%2F1': { points: pts([1e6, 2.5e6]) },
      'GET /api/telemetry/series?device=sw-a-01&metric=out_bps&hours=6&port=Gi1%2F0%2F1': empty,
      'GET /api/telemetry/series?device=sw-a-01&metric=errors&hours=6&port=Gi1%2F0%2F1': empty })
    vi.stubGlobal('fetch', f.fn)
    renderWithApp(<DeviceGraphs name="sw-a-01" interfaces={[iface('Gi1/0/1')]} />)
    expect(await screen.findByText('CPU')).toBeInTheDocument()
    expect(screen.getByText('20 %')).toBeInTheDocument()
    expect(screen.queryByText('Memory')).not.toBeInTheDocument()
    expect(screen.getByText('Gi1/0/1 in')).toBeInTheDocument()
    expect(screen.getByText('2.5 Mbit/s')).toBeInTheDocument()
    expect(screen.getAllByText('Nothing stored in this time range.')).toHaveLength(2)
  })

  it('says how graphs start when nothing is stored', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': crew,
      'GET /api/telemetry/series?device=fw-01&metric=cpu&hours=6': { points: [] },
      'GET /api/telemetry/series?device=fw-01&metric=mem&hours=6': { points: [] },
      'GET /api/telemetry/series?device=fw-01&metric=up&hours=6': { points: [] } }).fn)
    renderWithApp(<DeviceGraphs name="fw-01" interfaces={[]} />)
    expect(await screen.findByText('No graphs yet')).toBeInTheDocument()
    expect(screen.queryByText('Port')).not.toBeInTheDocument()
  })
})
