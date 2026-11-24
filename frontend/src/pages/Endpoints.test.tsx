import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Endpoints from './Endpoints'

afterEach(() => vi.unstubAllGlobals())

const crew = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['seats.view'] } }
const status = { store: 'database', written: 3, open: 1, keep_days: 7, error: null }
const row = {
  mac: '02:00:00:00:00:07', ip: '192.0.2.40', device: 'sw-a-01', port: 'Gi1/0/1', seat: 'A-1', vlan: 10,
  first_seen: 1_763_380_000, last_seen: 1_763_383_600,
}

describe('Endpoints', () => {
  it('finds an IP and links its port and seat history', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': crew,
      'GET /api/endpoints?q=192.0.2.40': { rows: [row, { ...row, port: null, seat: null, device: 'core-01' }], status },
    }).fn)
    renderWithApp(<Endpoints />, '/endpoints?q=192.0.2.40')
    expect(await screen.findByRole('link', { name: 'sw-a-01 Gi1/0/1' })).toHaveAttribute('href', '/endpoints?device=sw-a-01&port=Gi1%2F0%2F1')
    expect(screen.getByRole('link', { name: 'A-1' })).toHaveAttribute('href', '/endpoints?seat=A-1')
    expect(screen.getByText('only in ARP on core-01')).toBeInTheDocument()
  })

  it('shows a seat history and says when nothing was seen', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': crew, 'GET /api/endpoints?seat=B-2': { rows: [], status },
    }).fn)
    renderWithApp(<Endpoints />, '/endpoints?seat=B-2')
    expect(await screen.findByText('Not seen')).toBeInTheDocument()
    expect(screen.getByText('Seat B-2')).toBeInTheDocument()
    expect(screen.getByText('Nothing like it in the last 7 days.')).toBeInTheDocument()
  })

  it('opens with the newest sightings before anyone searches (issue #872)', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': crew, 'GET /api/endpoints': { rows: [row], status } }).fn)
    renderWithApp(<Endpoints />, '/endpoints')
    expect(await screen.findByRole('link', { name: 'sw-a-01 Gi1/0/1' })).toBeInTheDocument()
    expect(screen.getByText(/The newest sightings/)).toBeInTheDocument()
  })
})
