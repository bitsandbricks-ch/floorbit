import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DnsData, DnsSite } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import DnsView from './DnsView'

afterEach(() => vi.unstubAllGlobals())

// 60 named sites: more than one page of the "Top sites" table.
const sites: DnsSite[] = Array.from({ length: 60 }, (_, i) => ({
  site: `site${i + 1}.example.com`, category: 'other', lookups: 1000 - i, blocked: 0, clients_max: 5,
}))
const data: DnsData = {
  hours: [], lookups: 50_000, blocked: 100, block_share: 0.002, sites, named: 60, unnamed_lookups: 10,
  categories: [{ id: 'other', lookups: 40_000 }, { id: 'gaming', lookups: 9000 }], new: [], blocked_sites: [],
  min_clients: 5, plugins: 1, last_poll: 1, error: null,
}

describe('DNS page (#1343)', () => {
  it('pages the top sites at 50 and sorts them by lookups', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dns?hours=24': data }).fn)
    renderWithApp(<DnsView expanded />)
    const top = await screen.findByRole('table', { name: 'Top sites' })
    // A header row and 50 sites.
    expect(within(top).getAllByRole('row')).toHaveLength(51)
    expect(within(top).getAllByRole('row')[1]).toHaveTextContent('site1.example.com')
    const region = screen.getByRole('region', { name: 'Top sites' })
    fireEvent.click(within(region).getByRole('button', { name: '2' }))
    expect(await within(top).findByText('site60.example.com')).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Categories' })).getAllByRole('row')).toHaveLength(3)
    expect(screen.getByText('Nothing blocked.')).toBeInTheDocument()
  })

  it('keeps the small view to the five busiest sites', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/dns?hours=24': data }).fn)
    renderWithApp(<DnsView expanded={false} />)
    expect(await screen.findByText('site5.example.com')).toBeInTheDocument()
    expect(screen.queryByText('site6.example.com')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
