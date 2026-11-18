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
    const [, theirs] = await screen.findAllByRole('button', { name: 'Limit dashboards' })
    fireEvent.click(theirs)
    const picker = screen.getByPlaceholderText('Every dashboard')
    fireEvent.click(picker)
    fireEvent.focus(picker)
    fireEvent.click(await screen.findByText('Hall B wall'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(sent).toEqual({ dashboards: ['hall-b'] }))
    expect(await screen.findByRole('button', { name: 'Only 1 dashboard' })).toBeInTheDocument()
  })
})
