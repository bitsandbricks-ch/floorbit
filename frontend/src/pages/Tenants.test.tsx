import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Tenants from './Tenants'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage'] } }
const list = {
  here: 'default',
  tenants: [
    { id: 'default', name: '', url: '', status: 'active' },
    { id: 'club-b', name: 'Club B', url: 'https://club-b.example.com', status: 'suspended' },
  ],
}

describe('Tenants', () => {
  it('lists the tenants and adds one with its first admin', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/platform/tenants': list,
      'POST /api/platform/tenants': {
        tenant: { id: 'club-c', name: 'Club C', url: '', status: 'active' }, admin: 'boss', password: 'example-password',
      },
      'PATCH /api/platform/tenants/club-b': { tenant: { ...list.tenants[1], status: 'active' } },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Tenants />)
    expect(await screen.findByText('Club B')).toBeInTheDocument()
    expect(screen.getByText('2 tenants')).toBeInTheDocument()
    expect(screen.getByText(/runs the platform and can't be suspended/)).toBeInTheDocument()
    // The default tenant can't be suspended; a suspended one can be taken back.
    expect(screen.queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Take back' }))
    fireEvent.change(screen.getByLabelText(/^Short name/), { target: { value: 'Club-C' } })
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Club C' } })
    fireEvent.change(screen.getByLabelText(/^First admin/), { target: { value: 'boss' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add tenant' }))
    const made = await screen.findByRole('status')
    expect(within(made).getByText('FLOORBIT_TENANT=club-c')).toBeInTheDocument()
    expect(within(made).getByText('example-password')).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ id: 'club-c', name: 'Club C', url: '', admin: 'boss' })
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ status: 'active' })
  })

  it('sets the admin of a tenant that is locked out', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/platform/tenants': list,
      'POST /api/platform/tenants/club-b/admin': { tenant: list.tenants[1], admin: 'boss', password: 'example-password', made: false },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Tenants />)
    expect(await screen.findByText('Club B')).toBeInTheDocument()
    // Only the other tenants: the default one's admins are on its Users page.
    expect(screen.getAllByRole('button', { name: 'Set admin' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Set admin' }))
    fireEvent.change(screen.getByLabelText(/^Admin's username/), { target: { value: ' boss ' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Set admin' })[1])
    const done = await screen.findByRole('status')
    expect(within(done).getByText(/boss is admin with a new password/)).toBeInTheDocument()
    expect(within(done).getByText('example-password')).toBeInTheDocument()
    expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ username: 'boss' })
  })
})

