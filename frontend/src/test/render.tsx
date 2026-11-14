import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '@/i18n'
import { Providers } from '@/Providers'

export function renderWithApp(ui: ReactElement, route = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return {
    client,
    ...render(
      <Providers client={client}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </Providers>,
    ),
  }
}

type Handler = (init: RequestInit | undefined) => { status?: number; body: unknown }

/** A fetch that answers from a table of "METHOD path" handlers and records the calls. */
export function fakeFetch(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; body: unknown }[] = []
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const route = routes[`${method} ${path}`]
    if (route === undefined) return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    const { status = 200, body } = typeof route === 'function' ? (route as Handler)(init) : { body: route }
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  return { fn, calls }
}
