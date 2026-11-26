import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { SeatTraffic } from './SeatTraffic'

afterEach(() => vi.unstubAllGlobals())

const answer = {
  seat: 'C-14', hours: 24, bytes: 184_000_000_000, stopped: false,
  categories: { downloads: 120_000_000_000, gaming: 48_000_000_000, streaming: 16_000_000_000 },
  applications: [{ name: 'LAN cache', category: 'downloads', bytes: 114_000_000_000 },
    { name: 'Counter-Strike 2', category: 'gaming', bytes: 41_000_000_000 }],
  owners: [{ asn: 64496, name: 'Example Transit', bytes: 46_000_000_000 }],
  agents: [{ name: 'Hall A', error: null }, { name: 'Hall B', error: 'timed out' }],
}

describe('SeatTraffic', () => {
  it('asks only on a click, because every look is audited', async () => {
    const fake = fakeFetch({ 'GET /api/traffic/seat/C-14': answer })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<SeatTraffic seat="C-14" />)
    expect(screen.getByText('Looking is written to the audit log.')).toBeInTheDocument()
    expect(fake.calls.some((c) => c.path.includes('/api/traffic/seat'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Show apps and destinations' }))
    expect(await screen.findByText('184 GB')).toBeInTheDocument()
    expect(screen.getByText('Counter-Strike 2').closest('tr')).toHaveTextContent('41.0 GB')
    expect(screen.getByText('Example Transit (AS64496)')).toBeInTheDocument()
    expect(screen.getByText('Hall B did not answer: timed out')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /C-14 by category: Gaming 26 %/ })).toBeInTheDocument()
  })
})
