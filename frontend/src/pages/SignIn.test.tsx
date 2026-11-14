import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { OidcList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import SignIn from './SignIn'

afterEach(() => vi.unstubAllGlobals())

const list: OidcList = {
  providers: [
    {
      id: 'authentik', name: 'Authentik', issuer: 'https://auth.example.com/application/o/floorbit', client_id: 'fb',
      scopes: 'openid profile email', role_claim: 'groups', role_mapping: [{ value: 'fb-techs', role: 'tech' }],
      secret_env: 'OIDC_AUTHENTIK_CLIENT_SECRET', secret_set: false, callback_url: 'https://floor.example.com/auth/oidc-authentik/callback',
    },
  ],
  roles: [{ id: 'tech', label: 'Tech' }, { id: 'viewer', label: 'Viewer' }],
  callback_template: 'https://floor.example.com/auth/oidc-ID/callback',
}
const routes = {
  'GET /api/auth/me': { enabled: true, user: { username: 'root', display_name: 'Root', role: 'admin', permissions: ['settings.manage'] } },
  'GET /api/settings/oidc': list,
}

describe('Sign-in providers page', () => {
  it('shows a provider, its mapping and the missing secret', async () => {
    vi.stubGlobal('fetch', fakeFetch(routes).fn)
    renderWithApp(<SignIn />)
    expect(await screen.findByText('Sign in with Authentik')).toBeInTheDocument()
    expect(screen.getByText('Secret missing')).toBeInTheDocument()
    expect(screen.getByText('OIDC_AUTHENTIK_CLIENT_SECRET')).toBeInTheDocument()
    expect(screen.getByText('Roles from the groups claim: fb-techs → Tech')).toBeInTheDocument()
  })

  it('adds a provider without ever asking for the secret', async () => {
    const api = fakeFetch({ ...routes, 'PUT /api/settings/oidc/keycloak': list })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<SignIn />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add provider' }))
    fireEvent.change(await screen.findByLabelText(/^Name/), { target: { value: 'Keycloak' } })
    fireEvent.change(screen.getByLabelText(/^Issuer URL/), { target: { value: 'https://id.example.com/realms/lan' } })
    fireEvent.change(screen.getByLabelText(/^Client ID/), { target: { value: 'floorbit' } })
    expect(screen.getByText('OIDC_KEYCLOAK_CLIENT_SECRET')).toBeInTheDocument()
    expect(screen.getByText('https://floor.example.com/auth/oidc-keycloak/callback')).toBeInTheDocument()
    expect(screen.queryByLabelText(/secret/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === 'PUT')?.body).toEqual({
        id: 'keycloak', name: 'Keycloak', issuer: 'https://id.example.com/realms/lan', client_id: 'floorbit',
        scopes: 'openid profile email', role_claim: 'groups', role_mapping: [],
      }),
    )
  })
})
