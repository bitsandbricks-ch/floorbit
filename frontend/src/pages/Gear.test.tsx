import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { GearData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Gear from './Gear'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }
const at = 1_763_100_000
const data: GearData = {
  items: [
    { id: 'd1', name: 'sw-spare-01', role: 'switch', model: 'Example 48P', serial: 'EXAMPLE1', origin: 'netbox', placed: false, loan: null },
    { id: 'd2', name: 'ap-hall2-01', role: 'access-point', model: '', serial: '', origin: 'manual', placed: true, loan: { to: 'Hall 2 stage', kind: 'area', by: 'Ben', at, note: '' } },
  ],
  log: [{ device_id: 'd2', name: 'ap-hall2-01', action: 'out', to: 'Hall 2 stage', kind: 'area', by: 'Ben', at, note: '' }],
  people: [{ username: 'ana', display_name: 'Ana' }],
}

describe('Gear', () => {
  it('lists gear, filters what is out, and checks a piece out', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/gear': data, 'POST /api/gear/d1/out': { to: 'Ana' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Gear />)
    expect(await screen.findByText('sw-spare-01')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Out (1)'))
    expect(screen.queryByText('sw-spare-01')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('All'))
    fireEvent.click(screen.getByRole('button', { name: 'Check out' }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Who' }), { target: { value: 'Ana' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Check out' }).at(-1)!)
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/gear/d1/out'
      && JSON.stringify(c.body) === JSON.stringify({ to: 'Ana', kind: 'person', note: '', until: null }))).toBe(true))
  })
  it('asks when a piece is due back, and flags overdue loans (issue #426)', async () => {
    const late: GearData = { ...data, items: [
      { ...data.items[0], loan: { to: 'Ana', kind: 'person', by: 'Ben', at, note: '', until: at + 3600, overdue: true } },
      { ...data.items[1], loan: { ...data.items[1].loan!, until: at + 7200, overdue: false } },
      { ...data.items[0], id: 'd3', name: 'sw-spare-03' },
    ] }
    const api = fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/gear': late, 'POST /api/gear/d3/out': { to: 'Ana' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Gear />)
    expect(await screen.findByText(/^Overdue since/)).toBeInTheDocument()
    expect(screen.getByText(/^Back by/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Overdue (1)'))
    expect(screen.getByText('sw-spare-01')).toBeInTheDocument()
    expect(screen.queryByText('ap-hall2-01')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('All'))
    fireEvent.click(screen.getAllByRole('button', { name: 'Check out' })[0])
    fireEvent.change(await screen.findByRole('combobox', { name: 'Who' }), { target: { value: 'Ana' } })
    fireEvent.change(screen.getByLabelText('Back by (optional)'), { target: { value: '2030-01-02T20:00' } })
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Check out' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/gear/d3/out'
      && (c.body as { until: number }).until === new Date('2030-01-02T20:00').getTime() / 1000)).toBe(true))
  })

  it('says who has what and filters to one holder', async () => {
    const loan = (to: string) => ({ to, kind: 'person' as const, by: 'Ben', at, note: '' })
    const lots: GearData = { ...data, items: [
      ...data.items,
      { ...data.items[0], id: 'd3', name: 'ap-spare-02', loan: loan('Ana') },
      { ...data.items[0], id: 'd4', name: 'sw-spare-03', loan: loan('Ana') },
    ] }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/gear': lots }).fn)
    renderWithApp(<Gear />)
    const holders = await screen.findByRole('group', { name: 'Who has what' })
    const buttons = within(holders).getAllByRole('button').map((b) => b.textContent)
    expect(buttons).toEqual(['Ana · 2 pieces', 'Hall 2 stage · 1 piece'])
    fireEvent.click(within(holders).getByRole('button', { name: 'Ana · 2 pieces' }))
    expect(screen.getByText('ap-spare-02')).toBeInTheDocument()
    expect(screen.queryByText('ap-hall2-01')).not.toBeInTheDocument()
    expect(screen.queryByText('sw-spare-01')).not.toBeInTheDocument()
    fireEvent.click(within(holders).getByRole('button', { name: 'Ana · 2 pieces' }))
    expect(screen.getByText('sw-spare-01')).toBeInTheDocument()
  })

  it('checks in everything one holder has', async () => {
    const loan = (to: string) => ({ to, kind: 'person' as const, by: 'Ben', at, note: '' })
    const lots: GearData = { ...data, items: [
      ...data.items,
      { ...data.items[0], id: 'd3', name: 'ap-spare-02', loan: loan('Ana') },
      { ...data.items[0], id: 'd4', name: 'sw-spare-03', loan: loan('Ana') },
    ] }
    const api = fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/gear': lots, 'POST /api/gear/d3/in': {}, 'POST /api/gear/d4/in': {} })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Gear />)
    const holders = await screen.findByRole('group', { name: 'Who has what' })
    expect(within(holders).queryByRole('button', { name: /All back/ })).not.toBeInTheDocument()
    fireEvent.click(within(holders).getByRole('button', { name: 'Ana · 2 pieces' }))
    fireEvent.click(within(holders).getByRole('button', { name: 'All back (2)' }))
    fireEvent.change(await screen.findByRole('textbox', { name: 'Note' }), { target: { value: 'teardown' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check in 2 pieces' }))
    await waitFor(() => expect(api.calls.filter((c) => c.method === 'POST').map((c) => [c.path, c.body])).toEqual([
      ['/api/gear/d3/in', { note: 'teardown' }], ['/api/gear/d4/in', { note: 'teardown' }],
    ]))
    expect(api.calls.some((c) => c.path === '/api/gear/d2/in')).toBe(false)
  })

  it('opens on one holder from ?holder=', async () => {
    window.history.pushState({}, '', '/gear?holder=Hall%202%20stage')
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/gear': data }).fn)
    renderWithApp(<Gear />)
    expect(await screen.findByText('ap-hall2-01')).toBeInTheDocument()
    expect(screen.queryByText('sw-spare-01')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hall 2 stage · 1 piece' })).toHaveAttribute('aria-pressed', 'true')
    window.history.pushState({}, '', '/')
  })
})
