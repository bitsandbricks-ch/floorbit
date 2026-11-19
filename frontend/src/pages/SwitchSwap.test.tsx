import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import SwitchSwap from './SwitchSwap'
import type { SwapPlan } from './switchSwap/types'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit', 'configs.read'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const plan: SwapPlan = {
  switch: { id: 'sw1', name: 'sw-a-01', model: 'C2960X', serial: 'OLD1', mgmt_ip: '192.0.2.11', status: 'down', since: 1_763_100_000 },
  spares: [{ id: 'sp1', name: 'spare-1', model: 'C2960X', serial: 'NEW1', same_model: true }],
  config: { id: 'c1', at: 1_763_000_000 }, config_readable: true,
  seat_ports: [{ port: 'Gi1/0/1', seat: 'A-1' }, { port: 'Gi1/0/2', seat: 'A-2' }],
  incident: { id: 'i1', title: 'sw-a-01 is down' }, swaps: [],
}
const entry = { at: 1_763_200_000, by: 'Ana', old_serial: 'OLD1', old_model: 'C2960X', new_serial: 'NEW1', new_model: 'C2960X', spare_id: 'sp1' }
const after: SwapPlan & { swap: typeof entry } = {
  ...plan, switch: { ...plan.switch, serial: 'NEW1' }, spares: [], swaps: [entry], swap: entry,
}

function show() {
  renderWithApp(<Routes><Route path="/switch-swap/:id" element={<SwitchSwap />} /></Routes>, '/switch-swap/sw1')
}

describe('Swap a switch', () => {
  it('walks the steps and swaps with the picked spare', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/switch-swap/sw1': plan, 'POST /api/switch-swap/sw1': after })
    vi.stubGlobal('fetch', api.fn)
    show()
    expect(await screen.findByText('Swap sw-a-01')).toBeInTheDocument()
    expect(screen.getByText('spare-1')).toBeInTheDocument()
    expect(screen.getByText('Gi1/0/2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download the last copy' })).toHaveAttribute('href', '/api/configs/sw-a-01/c1?download=1')
    fireEvent.click(screen.getByRole('button', { name: 'Swapped: the spare is in' }))
    expect(await screen.findByText(/now has serial number NEW1/)).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && JSON.stringify(c.body) === '{"spare_id":"sp1"}')).toBe(true))
  })

  it('takes a typed serial when no spare is on the shelf', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/switch-swap/sw1': { ...plan, spares: [] }, 'POST /api/switch-swap/sw1': after })
    vi.stubGlobal('fetch', api.fn)
    show()
    expect(await screen.findByText('No switch of this kind is on the shelf in the inventory.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Swapped: the spare is in' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Its serial number/), { target: { value: 'FOC1' } })
    fireEvent.click(button)
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && JSON.stringify(c.body) === '{"serial":"FOC1","model":""}')).toBe(true))
  })

  it('lets a viewer read the plan but not swap', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/switch-swap/sw1': { ...plan, config: null, config_readable: false } }).fn)
    show()
    expect(await screen.findByText("Your role can't change the inventory.")).toBeInTheDocument()
    expect(screen.getByText(/can't read switch configs/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Swapped: the spare is in' })).not.toBeInTheDocument()
  })
})
