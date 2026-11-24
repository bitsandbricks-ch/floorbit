import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { FirewallLookup } from './Lookup'

afterEach(() => vi.unstubAllGlobals())

describe('Which firewall?', () => {
  it('looks up an IP and says its part and the firewall it takes now', async () => {
    const api = fakeFetch({
      'GET /api/firewalls/lookup?q=192.0.2.40': {
        query: '192.0.2.40', kind: 'ip', seat: null, found: true, intended: 'fw-02', now: 'fw-03', state: 'failover',
        range: 'Hall', range_id: 'r1', cidr: '192.0.2.0/26', part: '192.0.2.32/27', fallback: ['fw-03'],
      },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<FirewallLookup />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: ' 192.0.2.40 ' } })
    fireEvent.submit(screen.getByRole('textbox').closest('form') as HTMLFormElement)
    expect(await screen.findByText('192.0.2.40 goes through fw-03')).toBeInTheDocument()
    expect(screen.getByText('failed over from fw-02')).toBeInTheDocument()
    expect(screen.getByText('Hall, part 192.0.2.32/27')).toBeInTheDocument()
    expect(screen.getByText('Fallback: fw-03')).toBeInTheDocument()
  })

  it('opens with the seat from the link and says when no range covers it', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/firewalls/lookup?q=B-1': { query: 'B-1', kind: 'seat', seat: 'B-1', found: false },
    }).fn)
    renderWithApp(<FirewallLookup />, '/firewalls?q=B-1')
    expect(await screen.findByText('Seat B-1 is in no planned range.')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('B-1')
  })

  it('shows why an answer is missing', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/firewalls/lookup?q=Z-9': () => ({ status: 404, body: { error: 'Z-9 is neither an IP address nor a seat with an IP address.' } }),
    }).fn)
    renderWithApp(<FirewallLookup />, '/firewalls?q=Z-9')
    expect(await screen.findByText('Z-9 is neither an IP address nor a seat with an IP address.')).toBeInTheDocument()
  })
})
