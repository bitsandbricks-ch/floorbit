import { Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { useTenantEvents } from '@/api/tenantEvents'
import { StatusLine } from '@/components/StatusLine'
import { clock, formatWhen } from '@/lib/time'
import { type Board, TIME_RANGES, type TimeRange, boardName } from './dashboards/model'
import { nextInRotation, publicUrl, ScreenContext } from './dashboards/screen'
import { GridView } from './dashboards/GridView'
import { useIdle } from './plan/idle'
import { updated, useReloadOnUpdate } from './plan/update'
import './dashboards/dashboards.css'

/** One dashboard on a whole screen (``/dashboards/<id>``): no sidebar, the cursor hides while nobody
 *  moves it, and the page reloads itself after an update. ``?rotate=a,b,c&every=30`` moves on to the
 *  next dashboard every so many seconds (10 to 600), for a wall that shows several. */
export default function DashboardScreen() {
  const { t, i18n } = useTranslation()
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const next = nextInRotation(params.get('rotate'), id)
  const every = Math.min(600, Math.max(10, Number(params.get('every')) || 30))
  useEffect(() => {
    if (!next) return undefined
    const timer = window.setTimeout(() => navigate(`/dashboards/${encodeURIComponent(next)}?${params.toString()}`, { replace: true }), every * 1000)
    return () => window.clearTimeout(timer)
  }, [next, every, navigate, params])
  // First ask the open feed: a public dashboard on a screen nobody signed in to reads only that.
  // A plain fetch, since the API client sends a 401 to the sign-in page.
  const open = useQuery({
    queryKey: [...qk.board(id), 'public'],
    queryFn: async () => {
      const res = await fetch(publicUrl(id), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .catch(() => { throw new Error(i18n.t('common.offline')) })
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
  const asked = params.get('range') as TimeRange | null
  const range = asked && TIME_RANGES.includes(asked) ? asked : q.data?.range
  const source = useMemo(() => ({
    publicId: anonymous ? id : null, tiles: open.data?.tiles ?? {}, hall: params.get('hall') ?? '', range,
  }), [anonymous, id, open.data?.tiles, params, range])
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
  useEffect(() => { if (q.data) document.title = `${boardName(t, q.data)} · Floorbit` }, [q.data, t])
  // On unless the dashboard switched it off; the status line needs an account, a public wall shows the header only.
  const frame = q.data?.frame !== false
  return (
    <main className={`fb-board-show${idle ? ' idle' : ''}${q.data && !q.data.fit ? ' scroll' : ''}${frame ? ' framed' : ''}`}>
      {q.data && frame && <ScreenHead name={boardName(t, q.data)} next={next} now={now} account={!anonymous} />}
      {(open.isPending || q.isPending) && <LoadingState />}
      {/* A big screen that read the board once keeps showing it while the server is away (a restart,
          the Wi-Fi): a small note instead of a banner that pushed the panes aside. */}
      {q.error && !q.data && <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />}
      {q.error && q.data && <Text role="status" className="fb-board-stale" fw={700}>{t('dashboards.stale')}</Text>}
      {q.data && (
        <ScreenContext.Provider value={source}>
          <GridView sections={q.data.sections} fit={q.data.fit} cycle={q.data.cycle} />
        </ScreenContext.Provider>
      )}
      {q.data && frame && !anonymous && !open.isPending && <StatusLine />}
      {!(q.data && frame) && <Text className="fb-board-clock" fw={800} aria-label={t('dashboards.clock')}>{clock(now, i18n.language)}</Text>}
    </main>
  )
}

/** The slim line above a full-screen dashboard: what it is, which event and day, what comes next
 *  in a rotation, and the clock (mocks, scene 6). */
function ScreenHead({ name, next, now, account }: { name: string; next: string | null; now: Date; account: boolean }) {
  const { t, i18n } = useTranslation()
  const after = useQuery({
    queryKey: [...qk.board(next ?? ''), 'name'],
    // Plain fetches: a public wall must not be sent to the sign-in page for a name.
    queryFn: async () => {
      for (const url of [publicUrl(next!), ...(account ? [`/api/dashboards/${encodeURIComponent(next!)}`] : [])]) {
        const res = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }).catch(() => null)
        const body = res?.ok ? await res.json() as { board?: Board | null } & Partial<Board> : null
        const board = body && ('board' in body ? body.board : (body as Board))
        if (board?.name) return boardName(t, board)
      }
      return next!
    },
    enabled: !!next,
    staleTime: 300_000,
  })
  return (
    <header className="fb-screen-head">
      <b className="fb-screen-name">{name}</b>
      {account && <EventName />}
      <span>{formatWhen(now, { weekday: 'short', day: '2-digit', month: '2-digit' }, i18n.language)}</span>
      <span className="fb-screen-grow" />
      {next && <span className="fb-screen-next">{t('dashboards.nextBoard', { name: after.data ?? next })}</span>}
      <b className="fb-screen-clock" aria-label={t('dashboards.clock')}>{clock(now, i18n.language)}</b>
    </header>
  )
}

/** The event's name; the event list needs an account. */
function EventName() {
  const { t } = useTranslation()
  const events = useTenantEvents()
  const event = events?.events?.find((e) => e.id === events.current)
  return event ? <span>{event.name || t('tenantEvents.unnamed')}</span> : null
}
