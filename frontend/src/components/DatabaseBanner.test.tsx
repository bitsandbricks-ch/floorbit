import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, get } from '@/api/client'
import { fakeFetch } from '@/test/render'
import { DatabaseBanner } from './DatabaseBanner'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('Database banner', () => {
  it('says nothing while the database answers', async () => {
    const fake = fakeFetch({ 'GET /healthz': { ok: true, database: 'up' } })
    vi.stubGlobal('fetch', fake.fn)
    render(<DatabaseBanner />)
    await waitFor(() => expect(fake.calls.length).toBe(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows that it is down, for how long, and that it is back', async () => {
    let health = { ok: true, database: 'down', down_for: 125 }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /healthz': () => ({ body: health }) }).fn)
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<DatabaseBanner />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Database unavailable')
    expect(alert).toHaveTextContent("changes can't be saved")
    expect(alert).toHaveTextContent('Down for 2 minutes')
    health = { ok: true, database: 'up', down_for: 0 }
    await act(async () => { await vi.advanceTimersByTimeAsync(5_100) })
    expect(await screen.findByRole('status')).toHaveTextContent('Database back')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(6_100) })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('checks at once when a save came back "database unavailable"', async () => {
    let health = { ok: true, database: 'up' }
    const fake = fakeFetch({
      'GET /healthz': () => ({ body: health }),
      'GET /api/halls': () => ({ status: 503, body: { code: 'database_unavailable', error: 'The database is away' } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    render(<DatabaseBanner />)
    await waitFor(() => expect(fake.calls.length).toBe(1))
    health = { ok: true, database: 'down' }
    await expect(get('/api/halls')).rejects.toBeInstanceOf(ApiError)
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
  })
})
