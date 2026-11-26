import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StatusPageData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import NetworkStatus from './NetworkStatus'

afterEach(() => vi.unstubAllGlobals())

const at = 1_763_100_000
const data: StatusPageData = {
  state: 'operational', auto_state: 'operational', override: null, since: at - 300, checked_at: at,
  areas: [], crew_areas: [], recovered: [], recovered_at: null, crew_recovered: [],
  updates: [
    { id: 'u1', at: at - 600, text: 'Older update.', state: null, area: 'Block A' },
    { id: 'u2', at: at - 60, text: 'Newer update.', state: null, area: '' },
  ],
  public: true,
}

describe('status updates (issue #890)', () => {
  it('lists them in the shared table, newest first, with where they apply', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': { enabled: false }, 'GET /api/status-page': data }).fn)
    renderWithApp(<NetworkStatus />)
    const table = await screen.findByRole('table', { name: 'Updates' })
    expect(within(table).getByRole('columnheader', { name: /Posted/ })).toBeInTheDocument()
    const rows = within(table).getAllByRole('row').filter((r) => r.closest('tbody'))
    expect(rows.map((r) => within(r).queryByText(/update\.$/)?.textContent)).toEqual(['Newer update.', 'Older update.'])
    expect(within(rows[0]).getByText('Everywhere')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Block A')).toBeInTheDocument()
  })
})
