import { Anchor, Button, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { IconArrowLeft, IconBellOff, IconExternalLink } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { ProblemDetail } from '@/api/types'
import { Layout } from '@/components/Layout'
import { Panel } from '@/components/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { PageHead } from '@bitsandbricks/ui'
import { canReport, reportBody } from './problems/format'
import { ProblemFacts } from './problems/facts'
import { problemPlaces } from './problems/places'
import { FindingPanel } from './problems/FindingPanel'
import { MuteDialog } from './problems/MuteDialog'
import { muteBody, muteKind, type MuteTarget } from './problems/mute'

/** One problem (issue #882): what and where, since when, its incident, and where to look next. A
 *  problem is what Floorbit sees; an incident is the work someone does about it, made from here. */
export default function ProblemPage() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const client = useQueryClient()
  const key = [...qk.problems, 'one', id]
  const q = useQuery({
    queryKey: key, queryFn: () => get<ProblemDetail>(`/api/problems/${encodeURIComponent(id)}`), refetchInterval: 30_000,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  })
  const refresh = () => void client.invalidateQueries({ queryKey: qk.problems })
  useLiveEvent('alerts.changed', refresh)
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  const [target, setTarget] = useState<MuteTarget | null>(null)
  const [muteError, setMuteError] = useState<string | null>(null)
  const report = useMutation({ mutationFn: () => post('/api/incidents', reportBody(q.data!.problem)), onSuccess: refresh })
  const mute = useMutation({
    mutationFn: (v: MuteTarget & { minutes: number; reason: string }) =>
      post('/api/alerts/mutes', { ...muteBody(v), minutes: v.minutes, reason: v.reason }),
    onSuccess: () => { setTarget(null); refresh() },
    onError: (e) => setMuteError(e.message),
  })
  const back = <Anchor component={Link} to="/problems" size="sm"><IconArrowLeft size={14} style={{ verticalAlign: -2 }} /> {t('problem.back')}</Anchor>
  const gone = q.error instanceof ApiError && q.error.status === 404

  if (q.isPending) return <Layout title={t('problems.title')}><LoadingState /></Layout>
  if (!q.data) {
    return (
      <Layout title={t('problems.title')}>
        <PageHead title={t('problem.title')} back={back} />
        {gone ? <EmptyState title={t('problem.over')} description={t('problem.overDesc')} /> : <ErrorBanner error={q.error} />}
      </Layout>
    )
  }
  const { problem: p } = q.data
  const muteable = q.data.can_mute && (!!p.mute_id || p.kind === 'switch') && !p.muted
  const places = problemPlaces(q.data, t)
  return (
    <Layout title={p.title}>
      <PageHead back={back} title={p.title}
        eyebrow={t(`problems.kind.${p.kind}`)}
        desc={p.where}
        actions={<>
          {p.incident && (
            <Button variant="default" component="a" href={`/incidents?q=${encodeURIComponent(`id:${p.incident}`)}`}>{t('problems.incidentOpen')}</Button>
          )}
          {q.data.can_report && canReport(p) && !p.incident && (
            <Button onClick={() => report.mutate()} loading={report.isPending}>{t('problems.report')}</Button>
          )}
          {muteable && (
            <Button variant="default" leftSection={<IconBellOff size={16} />}
              onClick={() => { setMuteError(null); setTarget({ id: p.mute_id ?? p.switch_id ?? '', name: p.name ?? p.where, kind: muteKind(p.kind) }) }}>
              {t('problems.mute')}
            </Button>
          )}
        </>} />
      <ErrorBanner error={report.error} mb="md" />
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Panel title={t('problem.what')}>
          <ProblemFacts p={p} />
        </Panel>
        <Panel title={t('problem.next')}>
          {places.length ? (
            <Stack gap={6}>
              {places.map((x) => (
                <Group key={x.href} gap={6}><IconExternalLink size={14} aria-hidden="true" /><Anchor href={x.href} size="sm">{x.label}</Anchor></Group>
              ))}
            </Stack>
          ) : <Text size="sm" c="dimmed">{t('problem.nowhere')}</Text>}
        </Panel>
      </SimpleGrid>
      {q.data.finding && (
        <div style={{ marginTop: 'var(--mantine-spacing-md)' }}>
          <FindingPanel f={q.data.finding} canShut={!!q.data.can_shut} needsLogin={!!q.data.needs_login} />
        </div>
      )}
      <MuteDialog target={target} busy={mute.isPending} error={muteError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </Layout>
  )
}

