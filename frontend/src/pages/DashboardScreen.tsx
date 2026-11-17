import { Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { clock } from '@/lib/time'
import type { Board } from './dashboards/model'
import { publicUrl, ScreenContext } from './dashboards/screen'
import { GridView } from './dashboards/GridView'
import { useIdle } from './plan/idle'
import { updated, useReloadOnUpdate } from './plan/update'
import './dashboards/dashboards.css'

/** One dashboard on a whole screen (``/dashboards/<id>``): no sidebar, the cursor hides while nobody
 *  moves it, and the page reloads itself after an update. */
export default function DashboardScreen() {
  const { t, i18n } = useTranslation()
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  // First ask the open feed: a public dashboard on a screen nobody signed in to reads only that.
  // A plain fetch, since the API client sends a 401 to the sign-in page.
  const open = useQuery({
    queryKey: [...qk.board(id), 'public'],
    queryFn: async () => {
      const res = await fetch(publicUrl(id), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return (await res.json()) as { account: boolean; board: Board | null; tiles: Record<string, string>; app: string }
    },
    refetchInterval: 60_000,
    retry: 1,
  })
  const anonymous = !!open.data && !open.data.account && !!open.data.board
  const full = useQuery({
    queryKey: qk.board(id),
    queryFn: () => get<Board>(`/api/dashboards/${encodeURIComponent(id)}`),
    refetchInterval: 60_000,   // someone saved a change: the screen follows within a minute
    enabled: !open.isPending && !anonymous,
  })
  const q = anonymous ? { ...open, data: open.data!.board!, refetch: open.refetch } : full
  const source = useMemo(() => ({
    publicId: anonymous ? id : null, tiles: open.data?.tiles ?? {}, hall: params.get('hall') ?? '',
  }), [anonymous, id, open.data?.tiles, params])
  const idle = useIdle(3000)
  // Signed out, /api/version may need an account too: the public feed says which version runs.
  useReloadOnUpdate(!anonymous && !open.isPending)
  const firstApp = useRef<string | undefined>(undefined)
  const app = anonymous ? open.data?.app : undefined
  useEffect(() => {
    if (!app) return
    firstApp.current ??= app
    if (updated(firstApp.current, app)) window.location.reload()
  }, [app])
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => { if (q.data) document.title = `${q.data.name} · Floorbit` }, [q.data])
  return (
    <main className={`fb-board-show${idle ? ' idle' : ''}${q.data && !q.data.fit ? ' scroll' : ''}`}>
      {(open.isPending || q.isPending) && <LoadingState />}
      {q.error && <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && (
        <ScreenContext.Provider value={source}>
          <GridView sections={q.data.sections} fit={q.data.fit} cycle={q.data.cycle} />
        </ScreenContext.Provider>
      )}
      <Text className="fb-board-clock" fw={800} aria-label={t('dashboards.clock')}>{clock(now, i18n.language)}</Text>
    </main>
  )
}
