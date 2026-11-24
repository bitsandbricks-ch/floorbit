import { Badge, Button, Group, Stack, Text, type ButtonProps } from '@mantine/core'
import { IconArrowRight, IconBellOff, IconChevronLeft } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { ProblemDetail } from '@/api/types'
import { ago } from '@/lib/time'
import { inApp } from '@/nav/sections'
import { ProblemFacts } from '@/pages/problems/facts'
import { canReport, reportBody } from '@/pages/problems/format'
import { MuteDialog } from '@/pages/problems/MuteDialog'
import { muteBody, muteKind, type MuteTarget } from '@/pages/problems/mute'
import { problemPlaces } from '@/pages/problems/places'
import { EmptyState, ErrorBanner, LoadingState, PanelSection, StatusBadge } from '@bitsandbricks/ui'

/** One notification beside the list: what and where, what it cuts off, the things to do about it
 *  and where to look next. The same facts as the problem's own page (#1390), which "Open problem"
 *  leads to. `onLeave` closes the panel when a link leads to another page; `onBack` (phones) goes
 *  back to the list. */
export function NotifyDetail({ id, onLeave, onBack }: { id: string; onLeave: () => void; onBack?: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  // The problem page's own query key: opening it from here shows the answer at once.
  const q = useQuery({
    queryKey: [...qk.problems, 'one', id], queryFn: () => get<ProblemDetail>(`/api/problems/${encodeURIComponent(id)}`),
    refetchInterval: 30_000, retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  })
  const refresh = () => void client.invalidateQueries({ queryKey: qk.problems })
  const [target, setTarget] = useState<MuteTarget | null>(null)
  const [muteError, setMuteError] = useState<string | null>(null)
  const report = useMutation({ mutationFn: () => post('/api/incidents', reportBody(q.data!.problem)), onSuccess: refresh })
  const mute = useMutation({
    mutationFn: (v: MuteTarget & { minutes: number; reason: string }) =>
      post('/api/alerts/mutes', { ...muteBody(v), minutes: v.minutes, reason: v.reason }),
    onSuccess: () => { setTarget(null); refresh() },
    onError: (e) => setMuteError(e.message),
  })
  const back = onBack && (
    <Button variant="subtle" size="compact-sm" leftSection={<IconChevronLeft size={14} aria-hidden="true" />} onClick={onBack} mb="xs">
      {t('notifications.back')}
    </Button>
  )
  if (q.isPending) return <div className="fb-notify-detail-pad">{back}<LoadingState rows={4} /></div>
  if (!q.data) {
    const gone = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="fb-notify-detail-pad">
        {back}
        {gone ? <EmptyState title={t('problem.over')} description={t('problem.overDesc')} /> : <ErrorBanner error={q.error} />}
      </div>
    )
  }
  const p = q.data.problem
  const muteable = q.data.can_mute && (!!p.mute_id || p.kind === 'switch') && !p.muted
  const places = problemPlaces(q.data, t)
  return (
    <>
      <div className="fb-notify-detail-head">
        {back}
        <Group gap={6} mb={6}>
          <StatusBadge size="sm" state={p.level === 'down' ? 'down' : 'warn'} label={t(`problem.levels.${p.level}`)} />
          <Badge size="sm" variant="light" color="gray">{t(`problems.kind.${p.kind}`)}</Badge>
          {p.since ? <Text size="xs" c="dimmed" ff="monospace">{ago(p.since)}</Text> : null}
        </Group>
        <Text fw={650} size="lg" lh={1.3} style={{ overflowWrap: 'anywhere' }}>{p.title}</Text>
        {p.where && <Text size="sm" c="dimmed">{p.where}</Text>}
        <Group gap="xs" mt="sm">
          <LinkButton href={`/problems/${encodeURIComponent(p.id)}`} onLeave={onLeave} size="xs" variant="default" rightSection={<IconArrowRight size={14} aria-hidden="true" />}>
            {t('notifications.openProblem')}
          </LinkButton>
          {p.incident && (
            <LinkButton href={`/incidents?q=${encodeURIComponent(`id:${p.incident}`)}`} onLeave={onLeave} size="xs" variant="default">
              {t('problems.incidentOpen')}
            </LinkButton>
          )}
          {q.data.can_report && canReport(p) && !p.incident && (
            <Button size="xs" variant="default" onClick={() => report.mutate()} loading={report.isPending}>{t('problems.report')}</Button>
          )}
          {muteable && (
            <Button size="xs" variant="default" leftSection={<IconBellOff size={14} aria-hidden="true" />}
              onClick={() => { setMuteError(null); setTarget({ id: p.mute_id ?? p.switch_id ?? '', name: p.name ?? p.where, kind: muteKind(p.kind) }) }}>
              {t('problems.mute')}
            </Button>
          )}
        </Group>
        {report.error && <div style={{ marginTop: 8 }}><ErrorBanner error={report.error} mb={0} /></div>}
      </div>
      <PanelSection label={t('problem.what')}>
        <ProblemFacts p={p} />
      </PanelSection>
      <PanelSection label={t('problem.next')} border={false}>
        {places.length ? (
          <Stack gap={6}>
            {places.map((x) => (
              <LinkButton key={x.href} href={x.href} onLeave={onLeave} variant="default" justify="space-between" fullWidth
                rightSection={<IconArrowRight size={14} aria-hidden="true" />}>{x.label}</LinkButton>
            ))}
          </Stack>
        ) : <Text size="sm" c="dimmed">{t('problem.nowhere')}</Text>}
      </PanelSection>
      <MuteDialog target={target} busy={mute.isPending} error={muteError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </>
  )
}

// A page Flask draws (the plan with a switch picked) is a plain link; a React page goes through the
// router and closes the panel on the way.
function LinkButton({ href, onLeave, ...props }: ButtonProps & { href: string; onLeave: () => void; children: ReactNode }) {
  return (
    <Button {...props} renderRoot={(root) => inApp(href)
      ? <Link to={href} {...root} onClick={onLeave} />
      : <a href={href} {...root} />} />
  )
}
