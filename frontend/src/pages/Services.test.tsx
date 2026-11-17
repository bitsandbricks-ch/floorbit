import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Services as ServicesData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Services from './Services'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'le', display_name: 'Le', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vi', display_name: 'Vi', role: 'viewer', permissions: ['floorplan.view'] } }
const base = { status: 'up' as const, since: 1, checked_at: 2, error: '', history: [[1, 12], [2, 14]] as [number, number | null][] }
const data: ServicesData = {
  uplinks: [{ ...base, status: 'warn', id: 'u1', name: 'Provider A', device: 'core-01', port: 'Te1/0/48', capacity_mbps: 1000,
    probe_host: 'www.example.com', probe_port: 443, port_state: 'up', in_bps: 850e6, out_bps: 90e6, utilization: 0.85, latency_ms: 12.5, loss: 0.2 }],
  resolvers: [{ ...base, status: 'down', id: 'r1', name: 'Resolver 1', address: '192.0.2.53', lookup: 'example.com', rcode: 'SERVFAIL',
    answers: 0, latency_ms: 3, error: 'example.com: SERVFAIL' }],
  sites: [{ ...base, status: 'down', id: 's1', name: 'Steam', host: 'store.example.com', port: 443, latency_ms: null, loss: null,
    error: 'store.example.com does not answer on port 443.' }],
  lan_cache: { status: 'up', hit_ratio: 0.72, served_bytes: 120e9, bps: 4e8, disk: { used: 8e12, total: 10e12, ratio: 0.8 }, error: '', demo: false },
  interval: 30, last_poll: 2, via_agent: false, probe_ports: [53, 80, 443, 853], devices: ['core-01'],
}

describe('Services', () => {
  it('shows how full each line is, failing resolvers and the LAN cache', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/services': data }).fn)
    renderWithApp(<Services />)
    const line = await screen.findByRole('region', { name: 'Provider A' })
    expect(within(line).getByText('85%')).toBeInTheDocument()
    expect(within(line).getByText('In 850 Mbps · out 90.0 Mbps')).toBeInTheDocument()
    expect(within(line).getByText('12.5 ms · 20% lost · to www.example.com')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Resolver 1' })).getByText('example.com: SERVFAIL')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'LAN cache' })).getByText('72%')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add line' })).not.toBeInTheDocument()
  })

  it('lets the crew add a resolver', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/services': { ...data, resolvers: [] },
      'POST /api/services/resolvers': () => ({ status: 201, body: data.resolvers[0] }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add resolver' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name' }), { target: { value: 'Resolver 1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Address' }), { target: { value: '192.0.2.53' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Name to look up/ }), { target: { value: 'example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      name: 'Resolver 1', address: '192.0.2.53', lookup: 'example.com',
    }))
  })

  it('shows each internet site and adds the usual ones in one go', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/services': { ...data, sites: [] },
      'POST /api/services/sites/common': () => ({ status: 200, body: data }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Services />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add the usual sites' }))
    const site = await screen.findByRole('region', { name: 'Steam' })
    expect(within(site).getByText('store.example.com does not answer on port 443.')).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/services/sites/common')).toBe(true)
  })
})
