import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TimelineData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Timeline from './Timeline'

afterEach(() => vi.unstubAllGlobals())

const me = { enabled: false }
const at = 1_763_100_000
const page = (more: boolean, entries: TimelineData['entries']): TimelineData => ({
  entries, total: 3, more, kinds: ['change', 'sign-in', 'outage', 'incident', 'alert', 'deploy'],
  counts: { change: 1, 'sign-in': 4, outage: 1, incident: 1, alert: 0, deploy: 0 },
})

describe('Timeline', () => {
  it('lists entries by day, filters by kind and pages back', async () => {
    const calls: string[] = []
    const auth = fakeFetch({ 'GET /api/auth/me': me })
    const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/timeline')) return auth.fn(input, init)
      calls.push(path)
      const query = new URLSearchParams(path.split('?')[1] ?? '')
      return new Response(JSON.stringify(query.get('before')
          ? page(false, [{ t: at - 7200, kind: 'incident', title: 'Incident opened: Cable cut', target: 'seat A-1', severity: 'warn' }])
          : page(true, [
            { t: at, kind: 'change', title: 'Changed switch', target: 'sw-a-01', who: 'ana' },
            { t: at - 60, kind: 'outage', title: 'Switch went offline', target: 'sw-b-02', severity: 'down' },
          ])), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    vi.stubGlobal('fetch', fn)
    renderWithApp(<Timeline />)
    expect(await screen.findByText('Changed switch')).toBeInTheDocument()
    expect(screen.getByText('sw-a-01 · by ana')).toBeInTheDocument()
    expect(screen.getByText('Sign-ins (4)')).toBeInTheDocument()
    expect(calls[calls.length - 1]).toContain('kinds=change%2Coutage%2Cincident%2Calert%2Cdeploy')
    fireEvent.click(screen.getByRole('button', { name: 'Older entries' }))
    expect(await screen.findByText('Incident opened: Cable cut')).toBeInTheDocument()
    expect(calls.some((c) => c.includes(`before=${at - 60}`))).toBe(true)
    fireEvent.click(screen.getByText('Sign-ins (4)'))
    await waitFor(() => expect(calls[calls.length - 1]).not.toContain('kinds='))
    expect(screen.getByRole('link', { name: 'CSV' }).getAttribute('href')).toContain('/api/timeline.csv?')
  })
})
