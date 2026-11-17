import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

export const UPDATE_CHECK_MS = 5 * 60_000

/** Whether the server now runs another Floorbit than the one this page was loaded from. */
export function updated(first: string | undefined, now: string | undefined) {
  return !!first && !!now && first !== now
}

const RELOAD = () => window.location.reload()

/** A wall screen runs for days: once Floorbit is updated, it loads the page again, so it shows
 *  the new version instead of running the old one until somebody walks up and reloads it. */
export function useReloadOnUpdate(on: boolean, reload: () => void = RELOAD) {
  const q = useQuery({
    queryKey: qk.version, queryFn: () => get<{ app: string }>('/api/version'),
    enabled: on, refetchInterval: on ? UPDATE_CHECK_MS : false, staleTime: 0, retry: false,
  })
  const first = useRef<string | undefined>(undefined)
  const now = q.data?.app
  useEffect(() => {
    if (!on || !now) return
    first.current ??= now
    if (updated(first.current, now)) reload()
  }, [on, now, reload])
}
