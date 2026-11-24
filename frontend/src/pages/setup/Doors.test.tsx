import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PreflightBoard } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Setup from '../Setup'
import { DoorsCheck } from './Doors'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const at = 1_763_100_000
const failing: PreflightBoard = {
  groups: {
    switches: { at, by: null, items: [
      { id: 's1', name: 'sw-a-01', status: 'pass', detail: 'Reachable' },
      { id: 's3', name: 'sw-a-02', status: 'pass', detail: 'Reachable' },
      { id: 's2', name: 'sw-b-01', status: 'fail', detail: 'Not reachable' }] },
    uplinks: { at, by: null, items: [{ id: 'u1', name: 'sw-a-01 Te1/1/1', status: 'pass', detail: 'Uplink to dist-01' }] },
    services: null,
  },
  counts: { pass: 3, warn: 0, fail: 1, skip: 0 }, ready: false, complete: false,
}
const ready: PreflightBoard = {
  ...failing,
  groups: { ...failing.groups, switches: { at, by: 'Ana', items: [{ id: 's2', name: 'sw-b-01', status: 'pass', detail: 'Reachable' }] }, services: { at, by: 'Ana', items: [] } },
  counts: { pass: 2, warn: 0, fail: 0, skip: 0 }, ready: true, complete: true,
}

describe('Before doors open', () => {
  it('asks for fresh answers by itself, shows what fails and folds the passes', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': tech, 'POST /api/preflight/refresh': failing, 'POST /api/preflight/run': ready })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<DoorsCheck />)
    expect(await screen.findByText('Not every check has run')).toBeInTheDocument()
    expect(screen.getByText('sw-b-01')).toBeInTheDocument()
    expect(screen.queryByText('sw-a-01')).not.toBeInTheDocument()       // passes fold into one line
    expect(screen.getByText('2 more are OK.')).toBeInTheDocument()
    expect(screen.getByText('The 1 check is OK.')).toBeInTheDocument()
    expect(screen.getByText('Not checked yet.')).toBeInTheDocument()
    expect(screen.getAllByText(/by Floorbit$/)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Check now' }))
    expect(await screen.findByText('Ready for doors')).toBeInTheDocument()
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/preflight/run')).toBe(true))
  })

  it('shows the crew only the checks on the Set up page', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': viewer,
      'GET /api/setup': { needs_account: false, done: true },
      'POST /api/preflight/refresh': failing,
    }).fn)
    renderWithApp(<Setup />)
    expect(await screen.findByText('sw-b-01')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check now' })).not.toBeInTheDocument()
    expect(screen.queryByText(/steps done/)).not.toBeInTheDocument()
  })
})
