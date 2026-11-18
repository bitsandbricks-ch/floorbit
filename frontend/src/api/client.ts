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

/** Pages a signed-out visitor stays on. /setup makes the first account: before, the sidebar's own
 *  reads answered 401 there and sent the visitor to sign in, with no account to sign in with. */
const SIGNED_OUT_PAGES = new Set(['/login', '/setup'])

export function loginUrl(): string {
  const next = window.location.pathname + window.location.search
  return `/login?next=${encodeURIComponent(next)}`
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  // The language picked in the sidebar, so the server's error texts come in it too.
  const headers: Record<string, string> = { Accept: 'application/json', 'Accept-Language': i18next.language || 'en' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    // The laptop lost the event Wi-Fi, or the server is restarting: the browser's own text
    // ("Failed to fetch", "NetworkError when…") said nothing useful and was English only.
    throw new ApiError(i18next.t('common.offline'), 0, { code: 'offline' })
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (res.status === 401 && !SIGNED_OUT_PAGES.has(window.location.pathname)) {
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
