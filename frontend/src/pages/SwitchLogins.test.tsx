import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import SwitchLogins from './SwitchLogins'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['settings.manage'] } }
const stored = { id: 'c1', kind: 'ssh', scope: '*', username: 'ops', set_at: 1_763_100_000, set_by: 'Ana' }

describe('SwitchLogins', () => {
  it('lists logins without passwords, and stores one write-only', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin, 'GET /api/settings/credentials': { credentials: [stored] },
      'PUT /api/settings/credentials/ssh': { ...stored, id: 'c2', scope: 'sw-a-*', username: 'ops-a' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SwitchLogins />)
    expect(await screen.findByText('ops')).toBeInTheDocument()
    expect(screen.getByText('••••••• (write-only)')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'For' }), { target: { value: 'sw-a-*' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), { target: { value: 'ops-a' } })
    const password = screen.getByLabelText('Password')
    fireEvent.change(password, { target: { value: 'example-pass' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('The login for sw-a-* is stored.')).toBeInTheDocument()
    expect(password).toHaveValue('')                                  // gone from the page once stored
    await waitFor(() => expect(api.calls.find((c) => c.method === 'PUT')?.body)
      .toEqual({ scope: 'sw-a-*', username: 'ops-a', password: 'example-pass' }))
  })
})
