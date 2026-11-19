import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Account, AccountsList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Users from './Users'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const account = (username: string, extra: Partial<Account> = {}): Account => ({
  username, display_name: username.toUpperCase(), role: 'tech', role_label: 'Tech', has_password: true,
  identities: [], discord_id: '', created_by: null, dashboards: [], ...extra,
})
const roles = [
  { id: 'admin', label: 'Admin', description: 'Everything.' },
  { id: 'lead', label: 'Lead', description: 'Runs the crew.' },
  { id: 'tech', label: 'Tech', description: 'Fixes things.' },
]
const list = (users: Account[]): AccountsList => ({
  users, roles, me: 'ada', discord: true, oidc: [{ id: 'oidc:club', label: 'Club login' }],
})

describe('Users', () => {
  it('lists accounts, changes a role and links Discord', async () => {
    const helper = account('helper1', { identities: ['oidc:club'], created_by: 'oidc:club' })
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/users': list([account('ada', { role: 'admin' }), helper]),
      'PATCH /api/users/helper1': (init: RequestInit | undefined) => {
        const body = JSON.parse(String(init?.body))
        return { body: list([account('ada', { role: 'admin' }), { ...helper, ...(body.role ? { role: body.role } : {}),
          ...(body.discord_id ? { discord_id: body.discord_id, identities: ['discord', 'oidc:club'] } : {}) }]) }
      },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Users />)
    expect(await screen.findByText('HELPER1')).toBeInTheDocument()
    expect(screen.getByText('helper1 · linked: Club login · joined with Club login')).toBeInTheDocument()
    expect(screen.getByText('you')).toBeInTheDocument()
    const [mine, theirs] = screen.getAllByRole('combobox', { name: 'Role' })
    expect(mine).toBeDisabled()
    fireEvent.click(theirs)
    const listbox = await waitFor(() => document.getElementById(theirs.getAttribute('aria-controls') ?? '') as HTMLElement)
    fireEvent.click(within(listbox).getByRole('option', { name: 'Lead', hidden: true }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'PATCH' && (c.body as { role?: string }).role === 'lead')).toBe(true))

    fireEvent.click(screen.getAllByRole('button', { name: 'Link Discord' })[1])
    fireEvent.change(screen.getByLabelText('Discord user ID'), { target: { value: '123456789012345678' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/linked: Discord 123456789012345678, Club login/)).toBeInTheDocument()
  })

  it('adds an account and shows what the server refuses', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/users': list([account('ada', { role: 'admin' })]),
      'POST /api/users': (init: RequestInit | undefined) => {
        const body = JSON.parse(String(init?.body))
        return body.username === 'ada'
          ? { status: 400, body: { error: 'That username is taken.' } }
          : { status: 201, body: list([account('ada', { role: 'admin' }), account(body.username, { role: body.role })]) }
      },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Users />)
    await screen.findByText('ADA')
    const fill = (name: string) => {
      fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: name } })
      fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'long-enough-1' } })
      fireEvent.click(screen.getByRole('button', { name: 'Add account' }))
    }
    fill('ada')
    expect(await screen.findByText('That username is taken.')).toBeInTheDocument()
    fill('helper2')
    expect(await screen.findByText('Added helper2.')).toBeInTheDocument()
    expect(screen.getByText('HELPER2')).toBeInTheDocument()
    const sent = api.calls.filter((c) => c.method === 'POST').pop()?.body as Record<string, string>
    expect(sent).toMatchObject({ username: 'helper2', role: 'lead', password: 'long-enough-1' })
  })

  it('limits a wall screen account to some dashboards', async () => {
    const screenAccount = account('screen-1', { role: 'kiosk', role_label: 'Kiosk' })
    let sent: unknown = null
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/users': list([account('ada', { role: 'admin' }), screenAccount]),
      'GET /api/dashboards': { layouts: [{ id: 'hall-b', name: 'Hall B wall' }, { id: 'kiosk', name: 'Kiosk' }], pages: [] },
      'PATCH /api/users/screen-1': (init: RequestInit | undefined) => {
        sent = JSON.parse(String(init?.body))
        return { body: list([account('ada', { role: 'admin' }), { ...screenAccount, dashboards: ['hall-b'] }]) }
      },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Users />)
    // Only the screen's row offers it: the crew's own accounts aren't limited.
    const buttons = await screen.findAllByRole('button', { name: 'Limit dashboards' })
    expect(buttons).toHaveLength(1)
    fireEvent.click(buttons[0])
    const picker = screen.getByPlaceholderText('Every dashboard')
    fireEvent.click(picker)
    fireEvent.focus(picker)
    fireEvent.click(await screen.findByText('Hall B wall'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(sent).toEqual({ dashboards: ['hall-b'] }))
    expect(await screen.findByRole('button', { name: 'Only 1 dashboard' })).toBeInTheDocument()
  })

  it('gives and takes the platform admin flag, for a platform admin only', async () => {
    let flagged = false
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/users': { ...list([account('ada', { role: 'admin', platform_admin: true }), account('bob', { role: 'admin' }),
        account('helper1')]), platform: true },
      'PATCH /api/users/bob': (init: RequestInit | undefined) => {
        flagged = JSON.parse(String(init?.body)).platform_admin
        return { body: { ...list([account('ada', { role: 'admin', platform_admin: true }),
          account('bob', { role: 'admin', platform_admin: flagged }), account('helper1')]), platform: true } }
      },
      'GET /api/tenant/platform-access': { visits: true, shown: false },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Users />)
    expect(await screen.findByText('BOB')).toBeInTheDocument()
    expect(screen.getAllByText('Platform admin')).toHaveLength(1)
    // Only an admin can be one: the tech gets no button.
    expect(screen.getAllByRole('button', { name: 'Make platform admin' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Make platform admin' }))
    expect(await screen.findByText(/Make BOB a platform admin\?/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, go ahead' }))
    await waitFor(() => expect(flagged).toBe(true))
    expect(await screen.findAllByText('Platform admin')).toHaveLength(2)
    // Not on a tenant other than the default one: no visits card there.
    expect(screen.queryByText('Platform visits')).not.toBeInTheDocument()
  })

  it('hides the flag from other admins and lets a tenant turn platform visits off', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/users': list([account('ada', { role: 'admin' }), account('bob', { role: 'admin' })]),
      'GET /api/tenant/platform-access': { visits: true, shown: true },
      'PUT /api/tenant/platform-access': (init: RequestInit | undefined) => (
        { body: { visits: JSON.parse(String(init?.body)).visits, shown: true } }),
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Users />)
    expect(await screen.findByText('BOB')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Make platform admin' })).not.toBeInTheDocument()
    const visits = await screen.findByRole('switch', { name: /^Let platform admins come into this tenant/ })
    expect(visits).toBeChecked()
    fireEvent.click(visits)
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({ visits: false }))
    await waitFor(() => expect(visits).not.toBeChecked())
  })
})
