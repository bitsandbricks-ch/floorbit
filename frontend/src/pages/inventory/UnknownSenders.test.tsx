import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { UnknownSender } from '@/api/unknownSenders'
import { UnknownSenders } from './UnknownSenders'

afterEach(() => vi.unstubAllGlobals())

const editor = { enabled: true, user: { username: 'ed', display_name: 'Ed', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const now = Date.now() / 1000
const senders: UnknownSender[] = [
  { address: '203.0.113.7', name: 'sw-x-09', kinds: { syslog: 12, flow: 40 }, first: now - 3600, last: now - 60, agents: ['Hall agent'], ignored: false },
  { address: '203.0.113.8', name: '', kinds: { trap: 3 }, first: now - 600, last: now - 600, agents: [], ignored: true },
]

describe('Unknown senders (#1443)', () => {
  it('counts the ones not ignored, adds one to the inventory prefilled and ignores another', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/inventory/unknown-senders': { senders },
      'POST /api/inventory': () => ({ status: 201, body: {} }), 'POST /api/inventory/unknown-senders/ignore': { ignored: [] },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<UnknownSenders canEdit roles={['switch', 'router']} />)
    fireEvent.click(await screen.findByText('1 unknown sender'))
    const row = await screen.findByRole('group', { name: '203.0.113.7' })
    expect(within(row).getByText('Syslog, 12 lines')).toBeInTheDocument()
    expect(within(row).getByText(/through Hall agent/)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: '203.0.113.8' })).toBeNull()   // ignored: behind the switch
    fireEvent.click(within(row).getByRole('button', { name: 'Add to inventory' }))
    expect(within(row).getByLabelText('Name')).toHaveValue('sw-x-09')
    fireEvent.click(within(row).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(api.calls.find((c) => c.method === 'POST' && c.path === '/api/inventory')?.body)
      .toEqual({ name: 'sw-x-09', role: 'switch', mgmt_ip: '203.0.113.7' }))
    fireEvent.click(screen.getByLabelText('Ignored (1)'))
    fireEvent.click(within(await screen.findByRole('group', { name: '203.0.113.8' })).getByRole('button', { name: 'Stop ignoring' }))
    await waitFor(() => expect(api.calls.find((c) => c.path === '/api/inventory/unknown-senders/ignore')?.body)
      .toEqual({ address: '203.0.113.8', ignored: false }))
  })

  it('shows nothing while every sender is known', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/inventory/unknown-senders': { senders: [] } }).fn)
    renderWithApp(<UnknownSenders canEdit roles={['switch']} />)
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(/unknown sender/)).toBeNull()
  })
})
