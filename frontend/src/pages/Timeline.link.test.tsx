import { waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import Timeline from './Timeline'

afterEach(() => vi.unstubAllGlobals())

describe('a link into the changelog (issue #882)', () => {
  it('starts searched for the place a problem or incident page links with', async () => {
    const me = { enabled: true, user: { username: 'ana', display_name: 'Ana', role: 'admin', permissions: ['audit.read'] } }
    const calls: string[] = []
    const auth = fakeFetch({ 'GET /api/auth/me': me })
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/timeline')) return auth.fn(input, init)
      calls.push(path)
      return new Response(JSON.stringify({ entries: [], total: 0, more: false, kinds: [], counts: {} }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<Timeline />, '/timeline?q=sw-a-01')
    await waitFor(() => expect(calls.some((c) => new URLSearchParams(c.split('?')[1]).get('q') === 'sw-a-01')).toBe(true))
  })
})
