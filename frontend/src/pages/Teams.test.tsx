import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RolesList, Team } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Teams from './Teams'

afterEach(() => vi.unstubAllGlobals())

const roles: RolesList = {
  permissions: [
    { id: 'floorplan.view', label: 'See the floor plan' },
    { id: 'seats.view', label: 'See who sits where' },
  ],
  roles: [
    { id: 'admin', label: 'Admin', description: '', permissions: ['floorplan.view', 'seats.view'], builtin: true, users: 1 },
    { id: 'tech', label: 'Tech', description: '', permissions: ['floorplan.view', 'seats.view'], builtin: true, users: 0 },
    { id: 'helpdesk', label: 'Helpdesk', description: 'Front desk', permissions: ['seats.view'], builtin: false, users: 0 },
  ],
}
const teams: Team[] = [
  { id: 'infra', name: 'Infra', parent: null, depth: 0, members: [{ username: 'ana', role: 'lead', role_label: 'Lead' }] },
  { id: 'core', name: 'Core', parent: 'infra', depth: 1, members: [] },
]
const routes = {
  'GET /api/auth/me': { enabled: true, user: { username: 'root', display_name: 'Root', role: 'admin', permissions: ['accounts.manage'] } },
  'GET /api/roles': roles,
  'GET /api/teams': { teams },
  'GET /api/users': { users: [{ username: 'ana', display_name: 'Ana', role: 'lead' }, { username: 'bo', display_name: 'bo', role: 'tech' }] },
}

describe('Roles and teams page', () => {
  it('lists roles, built-in ones read-only, and the team tree with members', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<Teams />)
    const table = (await screen.findByText('Front desk')).closest('table')!
    const helpdesk = within(table).getByText('Helpdesk').closest('tr')!
    expect(within(helpdesk).getByRole('button', { name: 'Change' })).toBeInTheDocument()
    const tech = within(table).getByText('Tech').closest('tr')!
    expect(within(tech).queryByRole('button', { name: 'Change' })).toBeNull()
    expect(await screen.findByText('ana · Lead')).toBeInTheDocument()
    expect(screen.getByText('Nobody in this team yet.')).toBeInTheDocument()
  })

  it('makes a custom role with the permissions ticked', async () => {
    const api = fakeFetch({ ...routes, 'PUT /api/roles/front-desk': { id: 'front-desk', ...roles } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Teams />)
    fireEvent.click(await screen.findByRole('button', { name: 'New role' }))
    fireEvent.change(await screen.findByLabelText(/^Name/), { target: { value: 'Front desk' } })
    fireEvent.click(screen.getByLabelText('See who sits where: nicks, IPs, MACs and check-ins'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({
        id: 'front-desk', label: 'Front desk', description: '', permissions: ['floorplan.view', 'seats.view'],
      }),
    )
  })
})
