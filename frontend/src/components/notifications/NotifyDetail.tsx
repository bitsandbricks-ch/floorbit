import { Button } from '@mantine/core'
import { IconArrowRight, IconBellOff } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { ProblemDetail } from '@/api/types'
import { ago } from '@/lib/time'
import { ProblemFacts } from '@/pages/problems/facts'
import { canReport, reportBody } from '@/pages/problems/format'
import { MuteDialog } from '@/pages/problems/MuteDialog'
import { muteBody, muteKind, type MuteTarget } from '@/pages/problems/mute'
import { problemPlaces } from '@/pages/problems/places'
import { ErrorBanner, NotificationDetail, NotificationLink, NotificationLinks, NotificationTag, PanelSection } from '@bitsandbricks/ui'

/** One notification beside the list: what and where, what it cuts off, the things to do about it
 *  and where to look next. The same facts as the problem's own page (#1390), which "Open problem"
 *  leads to. */
export function NotifyDetail({ id }: { id: string }) {
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
  if (!q.data) {
    return <NotificationDetail loading={q.isPending} error={q.error}
      gone={q.error instanceof ApiError && q.error.status === 404} />
  }
  const p = q.data.problem
  const muteable = q.data.can_mute && (!!p.mute_id || p.kind === 'switch') && !p.muted
  return (
    <NotificationDetail
      state={p.level === 'down' ? 'down' : 'warn'} stateLabel={t(`problem.levels.${p.level}`)}
      tags={<NotificationTag>{t(`problems.kind.${p.kind}`)}</NotificationTag>}
      time={p.since ? ago(p.since) : undefined} title={p.title} where={p.where}
      actions={<>
        <NotificationLink href={`/problems/${encodeURIComponent(p.id)}`} size="xs" variant="default"
          rightSection={<IconArrowRight size={14} aria-hidden="true" />}>
          {t('notifications.openProblem')}
        </NotificationLink>
        {p.incident && (
          <NotificationLink href={`/incidents?q=${encodeURIComponent(`id:${p.incident}`)}`} size="xs" variant="default">
            {t('problems.incidentOpen')}
          </NotificationLink>
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
      </>}
    >
      {report.error && <div style={{ padding: '8px 18px 0' }}><ErrorBanner error={report.error} mb={0} /></div>}
      <PanelSection label={t('problem.what')}>
        <ProblemFacts p={p} />
      </PanelSection>
      <NotificationLinks links={problemPlaces(q.data, t)} />
      <MuteDialog target={target} busy={mute.isPending} error={muteError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </NotificationDetail>
  )
}
