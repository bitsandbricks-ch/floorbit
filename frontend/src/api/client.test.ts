import { afterEach, describe, expect, it, vi } from 'vitest'
import { get } from './client'

function signedOut() {
  return vi.fn(async () => new Response(JSON.stringify({ error: 'Sign in required' }), { status: 401 }))
}

describe('a 401 from the API', () => {
  const assign = vi.fn()
  afterEach(() => {
    vi.unstubAllGlobals()
    assign.mockReset()
    window.history.replaceState(null, '', '/')
  })

  function at(path: string) {
    window.history.replaceState(null, '', path)
    vi.stubGlobal('location', { ...window.location, pathname: path, search: '', assign })
    vi.stubGlobal('fetch', signedOut())
  }

  it('sends a signed-out visitor to sign in, and back after', async () => {
    at('/problems')
    await get('/api/problems').catch(() => undefined)
    expect(assign).toHaveBeenCalledWith('/login?next=%2Fproblems')
  })

  it('leaves the first-run setup alone: there is no account to sign in with yet', async () => {
    at('/setup')
    await get('/api/pages').catch(() => undefined)
    expect(assign).not.toHaveBeenCalled()
  })

  it('leaves the sign-in page alone (a wrong password)', async () => {
    at('/login')
    await get('/api/auth/me').catch(() => undefined)
    expect(assign).not.toHaveBeenCalled()
  })
})
