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

  it('zooms with the buttons and back to everything with Show everything', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/links': data }).fn)
    renderWithApp(<Topology />)
    const svg = await screen.findByRole('img', { name: 'Topology with 2 links' })
    const whole = svg.getAttribute('viewBox')!
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    const closer = svg.getAttribute('viewBox')!.split(' ').map(Number)
    expect(closer[2]).toBeLessThan(Number(whole.split(' ')[2]))
    fireEvent.click(screen.getByRole('button', { name: 'Show everything' }))
    expect(svg.getAttribute('viewBox')).toBe(whole)
  })

  it('draws a link by picking two switches', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/links': data }).fn)
    renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    fireEvent.click(screen.getByRole('button', { name: 'Draw a link' }))
    expect(screen.getByText('Pick the switch the link starts at (Esc cancels).')).toBeInTheDocument()
    fireEvent.click(screen.getByText('sw-c-02', { selector: 'text' }))
    expect(screen.getByText('From sw-c-02: now pick the switch at the other end.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('core-01', { selector: 'text' }))
    expect(await screen.findByRole('dialog', { name: 'Add link' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('From switch')[0]).toHaveValue('sw-c-02')
    expect(screen.getAllByLabelText('To switch')[0]).toHaveValue('core-01')
  })

  it('keeps a dragged box where the crew put it, for everyone', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/links': data,
      'PUT /api/links/layout': (init?: RequestInit) => ({ status: 200, body: { layout: JSON.parse(String(init?.body)).positions } }),
    })
    vi.stubGlobal('fetch', api.fn)
    const { container } = renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    const box = container.querySelector('g[data-node="sw-c-02"]')!
    const before = box.getAttribute('transform')
    fireEvent.pointerDown(box, { button: 0, clientX: 10, clientY: 10, pointerId: 1 })
    fireEvent.pointerMove(box, { clientX: 30, clientY: 50, pointerId: 1 })
    fireEvent.pointerUp(box, { clientX: 30, clientY: 50, pointerId: 1 })
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')).toBeDefined())
    const sent = (api.calls.find((c) => c.method === 'PUT')!.body as { positions: Record<string, unknown> }).positions
    expect(Object.keys(sent).sort()).toEqual(['core-01', 'dist-01', 'sw-c-02'])   // every box, so the rest stays put
    await waitFor(() => expect(container.querySelector('g[data-node="sw-c-02"]')!.getAttribute('transform')).not.toBe(before))
  })

  it('lets viewers look around but not draw or drag', async () => {
    const viewer = { ...lead, user: { ...lead.user, role: 'viewer', permissions: ['floorplan.view'] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/links': data }).fn)
    renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    expect(screen.queryByRole('button', { name: 'Draw a link' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()
  })

  it('offers the switch ports in the link form, free ones first', async () => {
    const ports = [
      { name: 'Te1/1/1', state: 'up', speed_bps: 1e10, used_by: 'dist-01 Te1/0/2' },
      { name: 'Te1/1/2', state: 'down', speed_bps: null, used_by: '' },
    ]
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': lead, 'GET /api/links': data, 'GET /api/links/ports?switch=sw-c-02': { ports },
    }).fn)
    renderWithApp(<Topology />)
    await screen.findByRole('img', { name: 'Topology with 2 links' })
    fireEvent.click(screen.getByRole('button', { name: 'Draw a link' }))
    fireEvent.click(screen.getByText('sw-c-02', { selector: 'text' }))
    fireEvent.click(screen.getByText('core-01', { selector: 'text' }))
    await screen.findByRole('dialog', { name: 'Add link' })
    const field = screen.getAllByLabelText('Port')[0]
    fireEvent.focus(field)
    fireEvent.click(field)
    expect(await screen.findByText('Free')).toBeInTheDocument()
    expect(screen.getByText('Has a link')).toBeInTheDocument()
    expect(screen.getByText('to dist-01 Te1/0/2')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Te1\/1\/2/, hidden: true })).toHaveTextContent('Down')
  })
})
