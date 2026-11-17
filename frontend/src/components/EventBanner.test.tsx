import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch } from '@/test/render'
import { EventBanner } from './EventBanner'

afterEach(() => vi.unstubAllGlobals())

const events = [
  { id: 'main', name: 'LAN 2026', status: 'live' },
  { id: 'lan-2027', name: 'LAN 2027', status: 'planning' },
]

describe('Event banner', () => {
  it('says nothing on the live event', async () => {
    const fake = fakeFetch({ 'GET /api/tenant/events': { events, live: 'main', current: 'main' } })
    vi.stubGlobal('fetch', fake.fn)
    render(<EventBanner />)
    await waitFor(() => expect(fake.calls.length).toBe(1))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('names the event this browser works on and goes back to the live one', async () => {
    const fake = fakeFetch({
      'GET /api/tenant/events': { events, live: 'main', current: 'lan-2027' },
      'PUT /api/tenant/current': { ok: true },
    })
    vi.stubGlobal('fetch', fake.fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, href: 'http://localhost/plan?event=lan-2027', origin: 'http://localhost', assign })
    render(<EventBanner />)
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent('You are working on LAN 2027 (Planning)')
    expect(banner).toHaveTextContent('the live event, LAN 2026')
    screen.getByRole('button', { name: 'Back to the live event' }).click()
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/plan'))
    expect(fake.calls.find((c) => c.method === 'PUT')?.body).toEqual({ event: null })
  })
})
