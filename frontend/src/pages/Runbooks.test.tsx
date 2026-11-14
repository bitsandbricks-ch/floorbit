import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Runbook } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Runbooks from './Runbooks'

afterEach(() => vi.unstubAllGlobals())

const books: Runbook[] = [
  { id: 'r1', title: 'No internet at the seat', kinds: ['no-internet'], body: '1. Check the **cable**\n2. Renew the address', starter: true, updated_at: null, by: null },
  { id: 'r2', title: 'Slow connection', kinds: ['slow', 'no-internet'], body: '- Swap the cable', starter: false, updated_at: 1_763_100_000, by: 'lea' },
]

describe('Runbooks', () => {
  it('shows a runbook, marks shadowed kinds and saves an edit', async () => {
    const sent: { method: string; path: string; body: unknown }[] = []
    const auth = fakeFetch({ 'GET /api/auth/me': { enabled: false } })
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (!path.startsWith('/api/runbooks')) return auth.fn(input, init)
      const method = init?.method ?? 'GET'
      if (method !== 'GET') sent.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : null })
      const body = method === 'GET' ? { runbooks: books, kinds: ['no-internet', 'slow', 'power', 'switch-down', 'other'] } : books[1]
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    renderWithApp(<Runbooks />, '/runbooks?open=r2')
    expect(await screen.findByRole('heading', { name: 'Slow connection' })).toBeInTheDocument()
    expect(screen.getByText('Swap the cable')).toBeInTheDocument()
    expect(screen.getByText('A runbook higher up the list is used for some of these kinds.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('No internet at the seat'))
    expect(await screen.findByText('cable')).toBeInTheDocument()
    expect(screen.getByText('Starter')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Steps'), { target: { value: '1. Call the access team' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(sent).toContainEqual({
      method: 'PATCH', path: '/api/runbooks/r1', body: { title: 'No internet at the seat', kinds: ['no-internet'], body: '1. Call the access team' },
    }))
  })
})
