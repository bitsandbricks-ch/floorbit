import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Webhook } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Webhooks from './Webhooks'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const events = ['switch.down', 'switch.up', 'incident.opened', 'seat.checked_in']
const hook: Webhook = {
  id: 'h1', name: 'Ticket bot', url: 'https://hooks.example.com/floorbit', events: ['switch.down'], active: true,
  created_at: 1_790_000_000, created_by: 'ada',
  last: { at: 1_790_000_100, event: 'switch.down', delivery: 'd1', ok: false, status: 500, error: 'Answered 500', attempt: 2 },
  deliveries: [{ at: 1_790_000_100, event: 'switch.down', delivery: 'd1', ok: false, status: 500, error: 'Answered 500', attempt: 2 }],
}

describe('Webhooks', () => {
  it('shows hooks with their deliveries, pings one and adds another', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/webhooks': { webhooks: [hook], events },
      'POST /api/settings/webhooks/h1/test': { ok: true, status: 204, error: null },
      'POST /api/settings/webhooks': { webhook: { ...hook, id: 'h2', name: 'Scoreboard' }, secret: 'whsec_example' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Webhooks />)
    expect(await screen.findByText('Ticket bot')).toBeInTheDocument()
    expect(screen.getByText('last delivery failed')).toBeInTheDocument()
    expect(screen.getByText(/Answered 500 · try 2/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send a test' }))
    expect(await screen.findByText('The test went through (answered 204).')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Scoreboard' } })
    fireEvent.change(screen.getByLabelText('URL'), { target: { value: 'https://score.example.com/in' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Seat checked in/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Add webhook' }))
    expect(await screen.findByText('whsec_example')).toBeInTheDocument()
    await waitFor(() => {
      const sent = api.calls.find((c) => c.method === 'POST' && c.path === '/api/settings/webhooks')?.body as Record<string, unknown>
      expect(sent).toMatchObject({ name: 'Scoreboard', url: 'https://score.example.com/in' })
      expect(sent.events).toEqual(['switch.down', 'switch.up', 'incident.opened', 'seat.checked_in'])
    })
  })
})
