import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Applications from '../Applications'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const answer = {
  hours: 24, kinds: ['game', 'launcher', 'sitegroup'], categories: ['gaming'], sources: [], applications: [],
  synced: [{ id: 'a1', name: 'Tournament rules', on: true, ok: true, changed_at: 1, count: 3 }], frozen: true,
}
const good = {
  id: 'a1', name: 'Tournament rules', url: 'https://example.com/rules.json', every_hours: 24, on: true,
  at: 1, ok: true, error: null, changed_at: 1, count: 3,
  last_change: { added: { count: 2, names: ['Example Arena', 'Example Other'] }, changed: { count: 0, names: [] }, removed: { count: 1, names: ['Old'] } },
}
const failed = { ...good, id: 'b2', name: 'Broken list', url: 'https://example.org/list.txt', ok: false, error: 'Could not fetch it: Timeout.' }
const own = { ...good, id: 'floorbit', name: 'Floorbit list', url: 'https://example.net/applications.json', builtin: true, signed: true }

describe('Rule sources', () => {
  it('lists each source with how its last fetch went, and freezes them', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/applications?hours=24': answer,
      'GET /api/applications/sources': { sources: [good, failed, own], frozen: false },
      'PUT /api/applications/sources-frozen': { sources: [good, failed], frozen: true },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Applications />, '/applications')
    expect(await screen.findByText(/Tournament rules \(changed/)).toBeInTheDocument()
    expect(screen.getByText(/Rule sources frozen/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Rule sources' }))
    const ok = await screen.findByLabelText('Tournament rules')
    expect(within(ok).getByText('3 applications')).toBeInTheDocument()
    const broken = screen.getByLabelText('Broken list')
    expect(within(broken).getByText('Failed')).toBeInTheDocument()
    expect(within(broken).getByText('Could not fetch it: Timeout. The last good copy stays in use.')).toBeInTheDocument()
    // Floorbit's own list can be switched off, not moved or removed.
    const ownRow = screen.getByLabelText('Floorbit list')
    expect(within(ownRow).queryByRole('button', { name: 'Remove' })).toBeNull()
    expect(within(ownRow).queryByRole('button', { name: 'Move to top' })).toBeNull()
    expect(within(ownRow).getByText(/signed/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('switch', { name: /Freeze/ }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.method === 'PUT')?.body).toEqual({ frozen: true }))
  })

  it('adds a source', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/applications?hours=24': { ...answer, synced: [], frozen: false },
      'GET /api/applications/sources': { sources: [], frozen: false },
      'POST /api/applications/sources': good,
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Applications />, '/applications')
    fireEvent.click(await screen.findByRole('button', { name: 'Rule sources' }))
    expect(await screen.findByText('No sources yet.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Tournament rules' } })
    fireEvent.change(screen.getByLabelText(/^URL/), { target: { value: 'https://example.com/rules.json' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.method === 'POST')?.body)
      .toEqual({ name: 'Tournament rules', url: 'https://example.com/rules.json', every_hours: 24 }))
  })

  it('is not offered to someone who may only look', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/applications?hours=24': answer }).fn)
    renderWithApp(<Applications />, '/applications')
    expect(await screen.findByText(/Tournament rules \(changed/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rule sources' })).toBeNull()
  })

  it('says what the last fetch changed, with the names on demand', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/applications?hours=24': answer,
      'GET /api/applications/sources': { sources: [good], frozen: false },
    }).fn)
    renderWithApp(<Applications />, '/applications')
    fireEvent.click(await screen.findByRole('button', { name: 'Rule sources' }))
    const line = await screen.findByRole('button', { name: 'Last change: 2 new, 0 changed, 1 removed' })
    fireEvent.click(line)
    expect(screen.getByText('New: Example Arena, Example Other')).toBeInTheDocument()
    expect(screen.getByText('Removed: Old')).toBeInTheDocument()
  })
})
