import { fireEvent, screen, waitFor } from '@testing-library/react'
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

  it('tests and saves NetBox, then moves on', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/setup': state(),
      'POST /api/settings/test/netbox': { ok: true, message: 'Connected to NetBox 4.1' },
      'PUT /api/settings': {},
      'POST /api/setup/steps/netbox': state({ steps: { netbox: 'done' } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Setup />)
    fireEvent.change(await screen.findByLabelText('URL'), { target: { value: 'https://netbox.example.com' } })
    fireEvent.change(screen.getByLabelText(/API token/), { target: { value: 'example-token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test the connection' }))
    expect(await screen.findByText('Connected to NetBox 4.1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))
    await waitFor(() => expect(fake.calls.some((c) => c.path === '/api/setup/steps/netbox')).toBe(true))
    expect(fake.calls.find((c) => c.method === 'PUT')?.body).toEqual({
      'netbox.url': 'https://netbox.example.com', 'netbox.token': 'example-token', 'netbox.verify_ssl': true,
    })
    expect(await screen.findByText(/live status, ports/)).toBeInTheDocument()   // the LibreNMS step
  })

  it('skips steps without saving anything', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/setup': state({ steps: { netbox: 'skipped', librenms: 'skipped' } }),
      'POST /api/setup/steps/switches': {},
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Setup />)
    expect(await screen.findByText(/press S and click/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    await waitFor(() => expect(fake.calls.find((c) => c.path === '/api/setup/steps/switches')?.body).toEqual({ state: 'skipped' }))
    expect(fake.calls.some((c) => c.method === 'PUT')).toBe(false)
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
