import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePublicFeed } from './publicFeed'

afterEach(() => vi.unstubAllGlobals())

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('usePublicFeed', () => {
  it('keeps the last good data when the server goes away, and says so', async () => {
    let up = true
    vi.stubGlobal('fetch', vi.fn(async () => (up ? json(200, { n: 1 }) : Promise.reject(new TypeError('offline')))))
    const { result } = renderHook(() => usePublicFeed<{ n: number }>('/x.json', 60), { wrapper })
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }))
    const good = result.current.lastGood
    expect(result.current.stale).toBe(false)
    up = false
    result.current.retry()
    await waitFor(() => expect(result.current.stale).toBe(true))
    expect(result.current.data).toEqual({ n: 1 })
    expect(result.current.lastGood).toBe(good)
  })

  it('reads a 404 as switched off, not as a hiccup', async () => {
    const fetch = vi.fn(async () => json(404, { error: 'off' }))
    vi.stubGlobal('fetch', fetch)
    const { result } = renderHook(() => usePublicFeed('/x.json', 60), { wrapper })
    await waitFor(() => expect(result.current.off).toBe(true))
    expect(result.current.failed).toBe(false)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
