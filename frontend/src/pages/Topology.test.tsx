import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SwitchLink, Topology as TopologyData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Topology from './Topology'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const base = { note: '', media: 'fiber', state: 'up', issue: '' } as const
const up: SwitchLink = { ...base, id: 'l1', a: 'dist-01', a_port: 'Fo1/1/1', b: 'core-01', b_port: 'Fo1/0/1', type: 'fiber-sm', speed: 40, speed_bps: 4e10 }
const slow: SwitchLink = { ...base, id: 'l2', a: 'sw-c-02', a_port: 'Te1/1/1', b: 'dist-01', b_port: 'Te1/0/2', type: 'fiber-mm', speed: 10, speed_bps: 1e9, issue: 'slow' }
const data: TopologyData = {
  nodes: ['core-01', 'dist-01', 'sw-c-02', 'sw-d-01'].map((name) => ({ id: name, name, role: name === 'core-01' ? 'router' : 'switch', hall: '', unread: false, status: name === 'dist-01' ? 'offline' as const : 'online' as const })),
  links: [up, slow], uplinks: [],
  suggestions: [{ a: 'sw-d-01', a_port: 'Te1/1/1', b: 'dist-01', b_port: 'Te1/0/3', protocol: 'lldp', speed: 10 }],
  counts: { links: 2, down: 0, slow: 1 }, types: ['cat5e', 'cat6', 'cat6a', 'fiber-sm', 'fiber-mm', 'dac'], speeds: [1, 10, 25, 40, 100],
}

describe('Topology', () => {
  it('draws the links, names the slow one, and adds what LLDP saw', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/links': data,
      'POST /api/links': () => ({ status: 201, body: { ...slow, id: 'l3' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Topology />)
    expect(await screen.findByRole('img', { name: 'Topology with 2 links' })).toBeInTheDocument()
    expect(screen.getByText('1 link needs a look')).toBeInTheDocument()
    fireEvent.click(screen.getByText('sw-c-02 Te1/1/1 – dist-01 Te1/0/2 runs at 1G, planned 10G'))
    expect(await screen.findByText('Slower than planned', { selector: '.mantine-Badge-label' })).toBeInTheDocument()
    expect(screen.getAllByText('Fiber multi-mode')).toHaveLength(2)            // the panel and the legend
    expect(screen.getByText('No links yet: sw-d-01')).toBeInTheDocument()

    expect(screen.getByText('sw-d-01 Te1/1/1 – dist-01 Te1/0/3 (LLDP)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.click(await screen.findByRole('combobox', { name: 'Type' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Fiber multi-mode', hidden: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({
      a: 'sw-d-01', a_port: 'Te1/1/1', b: 'dist-01', b_port: 'Te1/0/3', type: 'fiber-mm', speed: 10, note: '',
    }))
  })

  it('flags a link whose port LLDP sees on another box as a wrong patch', async () => {
    const wrong: SwitchLink = { ...up, lldp: { state: 'other', at: 'a', remote: 'core-01', remote_port: 'Fo1/0/9' } }
    const seen: SwitchLink = { ...slow, issue: '', speed_bps: 1e10, lldp: { state: 'seen' } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/links': { ...data, links: [wrong, seen] } }).fn)
    renderWithApp(<Topology />)
    expect(await screen.findByText('1 link needs a look')).toBeInTheDocument()
    fireEvent.click(screen.getByText('dist-01 Fo1/1/1 – core-01 Fo1/0/1: dist-01 Fo1/1/1 sees core-01 Fo1/0/9, check the patch'))
    expect(await screen.findByText('Sees core-01 Fo1/0/9: check the patch')).toBeInTheDocument()
  })

  it('marks a box that is down and says so in its panel', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/links': data }).fn)
    const { container } = renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    expect(container.querySelector('rect[data-status="offline"]')).not.toBeNull()
    expect(container.querySelectorAll('rect[data-status="online"]')).toHaveLength(2)     // sw-d-01 has no links, so it isn't drawn
    fireEvent.click(screen.getByText('dist-01', { selector: 'text' }))
    expect(await screen.findByText('Down', { selector: '.mantine-Badge-label' })).toBeInTheDocument()
  })

  it('draws each internet line above its router, with its state in the panel', async () => {
    const lines = [
      { id: 'u1', name: 'ISP A', device: 'core-01', port: 'Te1/0/48', capacity_mbps: 10000, status: 'warn' as const, utilization: 0.85 },
      { id: 'u2', name: 'ISP B', device: 'core-01', port: 'Te1/0/47', capacity_mbps: 1000, status: 'down' as const, utilization: null },
      { id: 'u3', name: 'Lost', device: 'nope-01', port: 'Gi0/1', capacity_mbps: 100, status: 'up' as const, utilization: null },
    ]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/links': { ...data, uplinks: lines } }).fn)
    const { container } = renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    expect(container.querySelectorAll('.fb-uplink')).toHaveLength(2)        // a line on a box not drawn is left out
    expect(container.querySelector('.fb-uplink[data-status="down"] line')).toHaveAttribute('stroke-dasharray', '6 4')
    fireEvent.click(screen.getByText('ISP A', { selector: 'text' }))
    expect(await screen.findByText('Needs a look', { selector: '.mantine-Badge-label' })).toBeInTheDocument()
    expect(screen.getByText('core-01 Te1/0/48')).toBeInTheDocument()
    expect(screen.getByText('85 %')).toBeInTheDocument()
  })
})
