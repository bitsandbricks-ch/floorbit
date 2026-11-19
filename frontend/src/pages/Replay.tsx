import { Paper, Select, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EventReplayData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { EventReplay } from './replay/EventReplay'

/** The whole event played back on the floor plan, from the recording (floorbit/recording.py). */
export default function Replay() {
  const { t } = useTranslation()
  const [hall, setHall] = useState('')
  const hallArg = hall ? `?hall=${encodeURIComponent(hall)}` : ''
  const query = useQuery({
    queryKey: qk.replayEvent(hall), queryFn: () => get<EventReplayData>(`/api/replay/event${hallArg}`),
  })
  const data = query.data

  return (
    <Layout title={t('replay.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('replay.title')} desc={t('replay.intro')}
        actions={data && data.halls.length > 1 && (
          <Select aria-label={t('replay.hall')} value={data.hall} allowDeselect={false}
            data={data.halls.map((h) => ({ value: h.id, label: h.name }))}
            onChange={(v) => setHall(v ?? '')} />
        )} />
      {query.isPending ? <LoadingState />
        : query.error ? <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
          : !data?.frames.length ? <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('replay.event.empty')}</Text></Paper>
            : <EventReplay key={data.hall} data={data} />}
    </Layout>
  )
}
