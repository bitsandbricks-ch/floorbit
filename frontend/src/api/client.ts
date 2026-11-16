// Same-origin JSON calls to the Flask API. The session cookie goes along by default; Flask
// checks Origin on writes (auth/_same_origin), so no CSRF token is needed here.
import i18next from 'i18next'
import { DB_DOWN_EVENT } from './databaseHealth'

export class ApiError extends Error {
  status: number
  data: Record<string, unknown>

  constructor(message: string, status: number, data: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export function loginUrl(): string {
  const next = window.location.pathname + window.location.search
  return `/login?next=${encodeURIComponent(next)}`
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  // The language picked in the sidebar, so the server's error texts come in it too.
  const headers: Record<string, string> = { Accept: 'application/json', 'Accept-Language': i18next.language || 'en' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (res.status === 401 && window.location.pathname !== '/login') {
    // Signed out in another tab, or the session expired. On the sign-in page it's a wrong password.
    window.location.assign(loginUrl())
  }
  if (res.status === 503 && data.code === 'database_unavailable') {
    window.dispatchEvent(new Event(DB_DOWN_EVENT))   // the banner checks at once
  }
  if (!res.ok) {
    const message = typeof data.error === 'string' ? data.error : `HTTP ${res.status}`
    // e.g. the CSV import's line-by-line problems
    throw new ApiError(message, res.status, data)
  }
  return data as T
}

export const get = <T>(path: string) => api<T>('GET', path)
export const post = <T>(path: string, body: unknown = {}) => api<T>('POST', path, body)
export const put = <T>(path: string, body: unknown) => api<T>('PUT', path, body)
export const patch = <T>(path: string, body: unknown) => api<T>('PATCH', path, body)
export const del = <T>(path: string) => api<T>('DELETE', path)
