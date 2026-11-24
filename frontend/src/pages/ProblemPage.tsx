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
import { EmptyState, ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { ago, dateTime } from '@/lib/time'
import { PageHead, StatusBadge } from '@bitsandbricks/ui'
import { canReport, reportBody } from './problems/format'
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
        {gone ? <EmptyState title={t('problem.over')} desc={t('problem.overDesc')} /> : <ErrorBanner error={q.error} />}
      </Layout>
    )
  }
  const { problem: p, device } = q.data
  const muteable = q.data.can_mute && (!!p.mute_id || p.kind === 'switch') && !p.muted
  // Where to look next: what the problem points at, then its device, seat, logs and machines.
  const places: { label: string; href: string }[] = [
    ...(p.link ? [{ label: t('problem.source'), href: p.link }] : []),
    ...(device ? [{ label: t('problem.device', { name: device.name }), href: `/inventory/devices/${encodeURIComponent(device.id)}` }] : []),
    ...(p.seat ? [{ label: t('problem.seatOnPlan', { seat: p.seat }), href: `/plan?seat=${encodeURIComponent(p.seat)}` }] : []),
    ...(p.device && !p.seat ? [{ label: t('problem.onPlan', { name: p.device }), href: `/plan?switch=${encodeURIComponent(p.device)}` }] : []),
    ...(q.data.may_see_people && (p.seat || p.device) ? [{
      label: t('problem.logs'), href: p.seat ? `/logs?seat=${encodeURIComponent(p.seat)}` : `/logs?device=${encodeURIComponent(p.device ?? '')}` }] : []),
    ...(q.data.may_see_people && p.seat ? [{ label: t('problem.machines'), href: `/endpoints?seat=${encodeURIComponent(p.seat)}` }] : []),
  ]
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
          <Stack gap={6}>
            <Group gap="sm" wrap="nowrap">
              <Text size="sm" c="dimmed" w={150} style={{ flexShrink: 0 }}>{t('problem.level')}</Text>
              <StatusBadge size="sm" state={p.muted ? 'unknown' : p.level === 'down' ? 'down' : 'warn'} label={t(`problem.levels.${p.muted ? 'muted' : p.level}`)} />
            </Group>
            <Row label={t('problem.since')} value={p.since ? `${dateTime(p.since)} (${ago(p.since)})` : t('problem.sinceUnknown')} />
            {p.device && <Row label={t('problem.switch')} value={p.device} />}
            {p.seat && <Row label={t('problem.seat')} value={p.seat} />}
            {p.cause && <Text size="sm" c="down">{t('problems.behindCause', { name: p.cause })}</Text>}
            {(p.seats?.length ?? 0) > 0 && <Row label={t('problem.cutOff')} value={p.seats!.join(', ')} />}
            {(p.behind?.length ?? 0) > 0 && <Row label={t('problem.behind')} value={p.behind!.join(', ')} />}
            {p.muted && <Text size="sm" c="dimmed">{t('problems.mutedUntil', { time: dateTime(p.muted.until), who: p.muted.by ?? '?' })}{p.muted.reason ? ` · ${p.muted.reason}` : ''}</Text>}
          </Stack>
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
      <MuteDialog target={target} busy={mute.isPending} error={muteError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </Layout>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start">
      <Text size="sm" c="dimmed" w={150} style={{ flexShrink: 0 }}>{label}</Text>
      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{value}</Text>
    </Group>
  )
}
