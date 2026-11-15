import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApiToken } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import ApiTokens from './ApiTokens'

afterEach(() => vi.unstubAllGlobals())

const admin = { enabled: true, user: { username: 'ada', display_name: 'Ada', role: 'admin', permissions: ['floorplan.view', 'settings.manage', 'accounts.manage'] } }
const token: ApiToken = {
  id: 'a1b2c3d4', name: 'Scoreboard', role: 'viewer', role_label: 'Viewer', read_only: true, created_at: 1_790_000_000,
  created_by: 'ada', expires_at: null, expired: false, last_used_at: null,
}
const roles = { permissions: [], roles: [{ id: 'viewer', label: 'Viewer', description: '', permissions: [], builtin: true, users: 0 }] }

describe('ApiTokens', () => {
  it('lists tokens, makes one and shows its secret once', async () => {
    const api = fakeFetch({
      'GET /api/auth/me': admin,
      'GET /api/roles': roles,
      'GET /api/settings/api-tokens': { tokens: [token], max_days: 365 },
      'POST /api/settings/api-tokens': { token: { ...token, id: 'e5f6a7b8', name: 'Discord bot' }, secret: 'fbt_e5f6a7b8_example-secret' },
    })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<ApiTokens />)
    expect(await screen.findByText('Scoreboard')).toBeInTheDocument()
    expect(screen.getByText(/never expires · never used/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Discord bot' } })
    fireEvent.click(screen.getByRole('button', { name: 'Make token' }))
    expect(await screen.findByText('fbt_e5f6a7b8_example-secret')).toBeInTheDocument()
    const sent = api.calls.find((c) => c.method === 'POST')?.body as Record<string, unknown>
    expect(sent).toMatchObject({ name: 'Discord bot', role: 'viewer', read_only: true, expires_days: 90 })
  })
})
