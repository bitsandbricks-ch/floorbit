import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { qk } from '@/api/keys'
import { fakeFetch } from '@/test/render'
import { updated, useReloadOnUpdate } from './update'

afterEach(() => vi.unstubAllGlobals())

const wrapper = (client: QueryClient) => ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>

describe('reload on update', () => {
  it('counts only a real change of version', () => {
    expect(updated('1.2.0', '1.3.0')).toBe(true)
    expect(updated('1.2.0', '1.2.0')).toBe(false)
    expect(updated(undefined, '1.3.0')).toBe(false)
    expect(updated('1.2.0', undefined)).toBe(false)
  })

  it('reloads once the server runs another version, not before', async () => {
    let app = '1.2.0'
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/version': () => ({ body: { api: 1, app } }) }).fn)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const reload = vi.fn()
    renderHook(() => useReloadOnUpdate(true, reload), { wrapper: wrapper(client) })
    await waitFor(() => expect(client.getQueryData(qk.version)).toEqual({ api: 1, app: '1.2.0' }))
    expect(reload).not.toHaveBeenCalled()
    app = '1.3.0'
    await client.refetchQueries({ queryKey: qk.version })
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
  })

  it('asks nothing when off', () => {
    const api = fakeFetch({})
    vi.stubGlobal('fetch', api.fn)
    const client = new QueryClient()
    renderHook(() => useReloadOnUpdate(false, vi.fn()), { wrapper: wrapper(client) })
    expect(api.calls).toHaveLength(0)
  })
})
