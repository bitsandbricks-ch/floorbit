import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BlockPlan, CableList } from '@/api/types'
import { OPTIONS, pick } from '@/test/options'
import { fakeFetch, renderWithApp } from '@/test/render'
import WalkRow from './WalkRow'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const order: BlockPlan = { block: 'A', clashes: [], cables: ['A-1', 'A-2'].map((seat, n) => ({ seat, switch: 'sw-a-01', port: `Gi1/0/${n + 1}`, block: 'b1' })) }
const cables: CableList = { sources: [], cables: [] }

describe('WalkRow', () => {
  it('names the port that came up and puts the seat on it, asking before a swap', async () => {
    let assigns = 0
    const api = fakeFetch({
      ...OPTIONS, 'GET /api/auth/me': lead, 'GET /api/cables': cables,
      'GET /api/seat-blocks': [{ id: 'b1', name: 'A', cols: 2, rows: 1, hall_id: 'h' }],
      'POST /api/cables/block': order,
      'GET /api/cables/walk?switch=sw-a-01': { ups: [], syslog: true, since: 500 },
      'GET /api/cables/walk?switch=sw-a-01&since=500': {
        ups: [{ port: 'Gi1/0/7', at: 520, how: 'syslog' }, { port: 'Gi1/0/5', at: 510, how: 'syslog' }], syslog: true, since: 500 },
      'POST /api/cables/assign': () => (++assigns === 2
        ? { status: 409, body: { error: "sw-a-01 Gi1/0/5 is A-9's port.", other_seat: 'A-9' } }
        : { body: { cable: {}, changed: ['C-0001'], other_seat: '' } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<WalkRow />)
    fireEvent.click(await screen.findByRole('combobox', { name: 'Seat block' }))
    fireEvent.click(await screen.findByRole('option', { name: 'A (2)', hidden: true }))
    await pick('Switch', 'sw-a-01')
    fireEvent.click(await screen.findByRole('button', { name: 'Start with 2 seats' }))

    expect(await screen.findByRole('heading', { name: 'A-1' })).toBeInTheDocument()
    expect(await screen.findByText('sw-a-01 Gi1/0/7 came up', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.getByText(/syslog: a port shows up here within seconds/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "That's A-1" }))
    // Next seat; the port just used is not offered again, the older one is.
    expect(await screen.findByRole('heading', { name: 'A-2' })).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 Gi1/0/5 came up')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "That's A-2" }))
    expect(await screen.findByText("Gi1/0/5 is A-9's port in the plan.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Swap A-2 and A-9' }))
    expect(await screen.findByText('Done: 2 of 2 seats found')).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.path === '/api/cables/assign').map((c) => c.body)
    expect(sent).toEqual([
      { seat: 'A-1', switch: 'sw-a-01', port: 'Gi1/0/7', block: 'b1' },
      { seat: 'A-2', switch: 'sw-a-01', port: 'Gi1/0/5', block: 'b1' },
      { seat: 'A-2', switch: 'sw-a-01', port: 'Gi1/0/5', swap: true, block: 'b1' },
    ])
    await waitFor(() => expect(api.calls.some((c) => c.path === '/api/cables/walk?switch=sw-a-01&since=500')).toBe(true))
  })
})
