import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PreflightBoard } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Preflight from './Preflight'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const at = 1_763_100_000
const failing: PreflightBoard = {
  groups: {
    switches: { at, by: 'Ana', items: [{ id: 's1', name: 'sw-a-01', status: 'pass', detail: 'Reachable' }, { id: 's2', name: 'sw-b-01', status: 'fail', detail: 'Not reachable' }] },
    uplinks: { at, by: 'Ana', items: [{ id: 'u1', name: 'sw-a-01 Te1/1/1', status: 'pass', detail: 'Uplink to dist-01' }] },
    services: null,
  },
  counts: { pass: 2, warn: 0, fail: 1, skip: 0 }, ready: false, complete: false,
}
const ready: PreflightBoard = {
  ...failing,
  groups: { ...failing.groups, switches: { at, by: 'Ana', items: [{ id: 's2', name: 'sw-b-01', status: 'pass', detail: 'Reachable' }] }, services: { at, by: 'Ana', items: [] } },
  counts: { pass: 2, warn: 0, fail: 0, skip: 0 }, ready: true, complete: true,
}

describe('Pre-flight check', () => {
  it('shows each group and runs one again', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/preflight': failing, 'POST /api/preflight/run': ready })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Preflight />)
    expect(await screen.findByText('Not every check has run')).toBeInTheDocument()
    expect(screen.getByText('Not reachable')).toBeInTheDocument()
    expect(screen.getByText('Not run yet.')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Run again' })[0])
    expect(await screen.findByText('Ready for doors')).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && JSON.stringify(c.body) === '{"group":"switches"}')).toBe(true))
  })

  it('lets viewers look but not run', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/preflight': failing }).fn)
    renderWithApp(<Preflight />)
    expect(await screen.findByText('sw-b-01')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Run all checks' })).not.toBeInTheDocument()
  })
})
