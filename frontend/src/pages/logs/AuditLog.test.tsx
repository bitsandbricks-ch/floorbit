import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { AuditLog } from './AuditLog'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'audit.read'] } }
const areas = ['floor plan', 'ports', 'settings']
const entry = (n: number, extra = {}) => ({
  time: `2026-11-16T08:${String(n).padStart(2, '0')}:00+0000`, user: 'ada', area: 'ports', action: 'bounce',
  target: `sw-a-01 Gi1/0/${n}`, fields: [], ...extra,
})

describe('Audit log', () => {
  it('lists entries, pages back and filters through the link', async () => {
    const first = Array.from({ length: 100 }, (_, i) => entry(i % 60))
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/audit?limit=100&offset=0': { entries: [entry(1, { ok: false, fields: ['speed'] }), ...first.slice(1)], total: 101, areas },
      'GET /api/settings/audit?limit=100&offset=100': { entries: [entry(59, { user: null, action: 'sign in' })], total: 101, areas },
      'GET /api/settings/audit?q=Gi1%2F0%2F7&limit=100&offset=0': { entries: [entry(7)], total: 1, areas },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<AuditLog />)
    expect(await screen.findByText('Showing 100 of 101')).toBeInTheDocument()
    expect(screen.getAllByText('bounce · failed')).toHaveLength(2)   // the table, and the list phones get
    expect(screen.getByText('speed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show older' }))
    expect(await screen.findByText('nobody signed in')).toBeInTheDocument()
    expect(screen.getByText('Showing 101 of 101')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show older' })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'Gi1/0/7' } })
    expect(await screen.findByText('Showing 1 of 1')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('link', { name: 'Download CSV' })).toHaveAttribute(
      'href', '/api/settings/audit.csv?q=Gi1%2F0%2F7'))
  })

  it('says when nothing matches', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/settings/audit?limit=100&offset=0': { entries: [], total: 0, areas },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<AuditLog />)
    expect(await screen.findAllByText('Nothing logged yet, or nothing matches these filters.')).not.toHaveLength(0)
  })
})
