import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import FlowLookup from './FlowLookup'

afterEach(() => vi.unstubAllGlobals())

const lead = { enabled: true, user: { username: 'lee', display_name: 'Lee', role: 'lead', permissions: ['floorplan.view', 'traffic.investigate'] } }
const answer = {
  total: 412, bytes: 91_000_000, peers: 318, stopped: false, since: 0, until: 3600,
  agents: [{ name: 'Hall A', total: 412, error: null, oldest: null, stopped: false },
    { name: 'Hall B', total: null, error: 'timed out', oldest: null, stopped: false }],
  rows: [{
    t: 1_800_000_000, src: '192.0.2.45', dst: '203.0.113.17', src_seat: 'D-5', dst_seat: null, protocol: 'udp',
    sport: 6881, dport: 6881, bytes: 48_000_000, packets: 36_000, owner: { asn: 64496, name: 'Example Transit' },
    application: 'BitTorrent', agent: 'Hall A',
  }],
}

describe('FlowLookup', () => {
  it('needs something to look for and a reason, then shows what the agents found', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': lead, 'POST /api/traffic/lookup': answer })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<FlowLookup />, '/flow-lookup')
    const search = screen.getByRole('button', { name: 'Search' })
    expect(search).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Seat' }), { target: { value: 'D-5' } })
    expect(search).toBeDisabled()                                              // no reason yet
    fireEvent.change(screen.getByRole('textbox', { name: /Reason/ }), { target: { value: 'P2P flood, incident 42' } })
    fireEvent.click(search)
    expect(await screen.findByText('412 flows')).toBeInTheDocument()
    const row = screen.getByText('D-5 · 192.0.2.45').closest('tr')!
    expect(row).toHaveTextContent('Example Transit (AS64496)')
    expect(row).toHaveTextContent('udp/6881 → 6881')
    expect(row).toHaveTextContent('48.0 MB')
    expect(screen.getByText('Showing the newest 1.')).toBeInTheDocument()
    expect(screen.getByText('Hall B did not answer: timed out')).toBeInTheDocument()
    const sent = fake.calls.find((c) => c.method === 'POST')!.body as Record<string, unknown>
    expect(sent).toMatchObject({ seat: 'D-5', window: '1h', reason: 'P2P flood, incident 42' })
  })
})
