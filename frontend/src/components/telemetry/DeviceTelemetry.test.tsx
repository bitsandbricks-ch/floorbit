import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DeviceTelemetryActions, DeviceTelemetryStatus, TelemetryDevicesTable } from './DeviceTelemetry'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['settings.manage'] } }
const refused = { driver: 'snmp', kind: 'refused', address: '192.0.2.21:161', detail: 'recvfrom: connection refused' }
const devices = { devices: { 'sw-a-01': { seen: null, online: false, problems: [refused] }, 'core-01': { seen: Date.now() / 1000 - 30, online: true, problems: [] } } }

describe('Device telemetry', () => {
  it('says why a device is silent, on its own', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/telemetry/devices': devices }).fn)
    renderWithApp(<DeviceTelemetryStatus name="sw-a-01" />)
    expect(await screen.findByText(/SNMP polling: nothing listens on 192.0.2.21:161/)).toBeInTheDocument()
  })

  it('lists every device with its actions', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin, 'GET /api/telemetry/devices': devices }).fn)
    renderWithApp(<TelemetryDevicesTable />)
    expect(await screen.findByText('core-01')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Test now' })).toHaveLength(2)
  })

  it('tests a device now and shows the raw lines', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'POST /api/telemetry/test': { ok: true, name: 'sw-a-01', agent: 'Hall 2', took_ms: 840, points: 104,
        summary: { measurements: { fb_if: 52, fb_sys: 1 }, ports: 52, sys_name: 'sw-a-01.example.com' }, problems: [], notes: [],
        raw: ['fb_if,device=sw-a-01,ifName=Gi1/0/1 ifOperStatus=1i'] },
      'GET /api/telemetry/raw': { name: 'sw-a-01', known: true, agent: 'Hall 2', lines: ['fb_sys,device=sw-a-01 uptime=12i'] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<DeviceTelemetryActions name="sw-a-01" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Test now' }))
    expect(await screen.findByText('Answers')).toBeInTheDocument()
    expect(screen.getByText(/104 values, 52 ports/)).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ name: 'sw-a-01' })
    fireEvent.click(screen.getByRole('button', { name: 'Show the raw line' }))
    expect(screen.getByText(/ifOperStatus=1i/)).toBeInTheDocument()
  })
})
