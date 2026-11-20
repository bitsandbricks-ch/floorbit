import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SetupState } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Setup from './Setup'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'mike', display_name: 'Mike', role: 'admin', permissions: ['settings.manage'] } }
const state = (over: Partial<SetupState> = {}): SetupState => ({
  needs_account: false, done: false, can_set_up: true, steps: {}, netbox: false, librenms: false,
  switches: { total: 0, placed: 0 }, theme: 'floorbit', ...over,
})

describe('Setup', () => {
  it('creates the first admin with the setup code', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': { enabled: true, user: null },
      'GET /api/setup': { needs_account: true, done: false },
      'POST /api/setup/account': { status: 201, body: { username: 'mike' } },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Setup />)
    fireEvent.change(await screen.findByLabelText(/Setup code/), { target: { value: 'ABCD-2345' } })
    fireEvent.change(screen.getByLabelText(/Username/), { target: { value: 'mike' } })
    fireEvent.change(screen.getByLabelText(/^Password\s*\*?$/), { target: { value: 'first-admin-pw' } })
    fireEvent.change(screen.getByLabelText(/Password again/), { target: { value: 'first-admin-pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create the admin account' }))
    await waitFor(() => expect(fake.calls.some((c) => c.method === 'POST')).toBe(true))
    expect(fake.calls.find((c) => c.method === 'POST')).toMatchObject({
      path: '/api/setup/account', body: { code: 'ABCD-2345', username: 'mike', password: 'first-admin-pw' },
    })
  })

  it('lists what the event needs, says what each step misses and skips one', async () => {
    const checklist = { done: false, steps: [
      { id: 'event', state: 'look', href: '/schedule', facts: { name: true, dates: false, logo: false } },
      { id: 'inventory', state: 'done', href: '/inventory', facts: { devices: 37, netbox: true } },
      { id: 'monitoring', state: 'look', href: '/settings/agents', facts: { agents: 1, connected: 0, source: true } },
      { id: 'alerts', state: 'todo', href: '/settings/discord', facts: { discord: false, webhooks: 0 } },
      { id: 'crew', state: 'skipped', href: '/settings/users', facts: { users: 1, teams: 0 } },
    ] }
    const fake = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/setup': state(),
      'GET /api/setup/checklist': checklist,
      'POST /api/setup/steps/alerts': {},
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Setup />)
    expect(await screen.findByText('2 of 5 steps done')).toBeInTheDocument()
    expect(screen.getByText('Still missing: the dates (Schedule), a logo (optional).')).toBeInTheDocument()
    expect(screen.getByText('37 devices in the inventory.')).toBeInTheDocument()
    expect(screen.getByText('No agent is connected right now.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Set up: Monitoring: a local agent and live status' })).toHaveAttribute('href', '/settings/agents')
    expect(screen.getByRole('link', { name: 'Open: Inventory: switches and devices' })).toHaveAttribute('href', '/inventory')
    expect(screen.getByRole('button', { name: 'Undo skip' })).toBeInTheDocument()
    const alerts = document.querySelector('[data-step="alerts"]') as HTMLElement
    fireEvent.click(within(alerts).getByRole('button', { name: 'Skip' }))
    await waitFor(() => expect(fake.calls.find((c) => c.path === '/api/setup/steps/alerts')?.body).toEqual({ state: 'skipped' }))
    expect(screen.getByRole('button', { name: 'Done for now, open the floor plan' })).toBeInTheDocument()
  })

  it('tells someone else an admin is setting up', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'viewer', permissions: [] } },
      'GET /api/setup': { needs_account: false, done: false },
    }).fn)
    renderWithApp(<Setup />)
    expect(await screen.findByText('An admin is still setting up Floorbit.')).toBeInTheDocument()
  })
})
