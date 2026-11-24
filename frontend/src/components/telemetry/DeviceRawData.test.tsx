import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { DeviceRawData, DeviceTelemetryActions } from './DeviceTelemetry'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['settings.manage'] } }
const lines = [
  'fb_if,device=sw-a-01,ifName=Gi1/0/1 ifOperStatus=1i 1',
  'fb_if,device=sw-a-01,ifName=Gi1/0/2 ifOperStatus=2i 1',
  'fb_sys,device=sw-a-01 sysUpTime=12i 1',
]

describe('Raw data tab', () => {
  it('shows the lines and filters them by measurement and text', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin,
      'GET /api/telemetry/raw?name=sw-a-01': { name: 'sw-a-01', known: true, agent: 'Hall 2', lines } }).fn)
    renderWithApp(<DeviceRawData name="sw-a-01" />)
    expect(await screen.findByText('3 of 3 lines')).toBeInTheDocument()
    expect(screen.getByText(/Hall 2/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'fb_sys 1' }))
    expect(screen.getByText('1 of 3 lines')).toBeInTheDocument()
    expect(screen.queryByText(/Gi1\/0\/1/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'fb_sys 1' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter lines' }), { target: { value: 'gi1/0/2' } })
    expect(screen.getByText('1 of 3 lines')).toBeInTheDocument()
    expect(screen.getByText(/ifOperStatus=2i/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter lines' }), { target: { value: 'nope' } })
    expect(screen.getByText('No line matches the filter.')).toBeInTheDocument()
  })

  it('says when nothing came in yet', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin,
      'GET /api/telemetry/raw?name=sw-a-01': { name: 'sw-a-01', known: true, agent: 'Hall 2', lines: [] } }).fn)
    renderWithApp(<DeviceRawData name="sw-a-01" />)
    expect(await screen.findByText('Nothing received from this device yet.')).toBeInTheDocument()
  })

  it('leaves the Raw data button out where the page has the tab', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': admin }).fn)
    renderWithApp(<DeviceTelemetryActions name="sw-a-01" raw={false} />)
    expect(await screen.findByRole('button', { name: 'Test now' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Raw data' })).not.toBeInTheDocument()
  })
})
