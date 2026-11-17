import { Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { clock } from '@/lib/time'
import type { Board } from './dashboards/model'
import { SplitView } from './dashboards/SplitView'
import { useIdle } from './plan/idle'
import { useReloadOnUpdate } from './plan/update'
import './dashboards/dashboards.css'

/** One dashboard on a whole screen (``/dashboards/<id>``): no sidebar, the cursor hides while nobody
 *  moves it, and the page reloads itself after an update. */
export default function DashboardScreen() {
  const { t, i18n } = useTranslation()
  const { id = '' } = useParams()
  const q = useQuery({
    queryKey: qk.board(id),
    queryFn: () => get<Board>(`/api/dashboards/${encodeURIComponent(id)}`),
    refetchInterval: 60_000,   // someone saved a change: the screen follows within a minute
  })
  const idle = useIdle(3000)
  useReloadOnUpdate(true)
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => { if (q.data) document.title = `${q.data.name} · Floorbit` }, [q.data])
  return (
    <main className={`fb-board-show${idle ? ' idle' : ''}`}>
      {q.isPending && <LoadingState />}
      {q.error && <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && <SplitView node={q.data.root} cycle={q.data.cycle} />}
      <Text className="fb-board-clock" fw={800} aria-label={t('dashboards.clock')}>{clock(now, i18n.language)}</Text>
    </main>
  )
}
