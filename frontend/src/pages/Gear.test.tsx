import { fireEvent, screen, waitFor } from '@testing-library/react'
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
      && JSON.stringify(c.body) === JSON.stringify({ to: 'Ana', kind: 'person', note: '' }))).toBe(true))
  })
})
