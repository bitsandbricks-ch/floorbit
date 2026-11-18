import { useQuery } from '@tanstack/react-query'
import { ApiError, get } from '@/api/client'
import { qk } from '@/api/keys'

/** What a public page (status, stats wall, schedule, brackets, hall) reads: its JSON, fetched again
 *  every ``every`` seconds. When the server or network is gone for a while the page keeps the last
 *  good data and says how old it is (``stale``), so a big screen never shows a browser error.
 *  ``off`` is the server's 404: an admin switched the page off. */
export function usePublicFeed<T>(url: string, every: number) {
  const q = useQuery<T, Error>({
    queryKey: qk.publicFeed(url),
    queryFn: () => get<T>(url),
    refetchInterval: Math.max(10, every) * 1000,
    // Off is an answer, not a hiccup: no retries for it.
    retry: (n, err) => !(err instanceof ApiError && err.status === 404) && n < 1,
  })
  const off = q.error instanceof ApiError && q.error.status === 404
  return {
    data: off ? undefined : q.data,
    loading: q.isPending,
    off,
    failed: !off && q.isError && q.data === undefined,
    stale: !off && q.isError && q.data !== undefined,
    // When the last good answer came: a failed fetch keeps it.
    lastGood: q.dataUpdatedAt || null,
    retry: () => void q.refetch(),
  }
}

/** ``?screen=1``: the big-screen layout of a public page (no scrolling, larger type). */
export function isScreen(search = window.location.search): boolean {
  return new URLSearchParams(search).get('screen') === '1'
}
