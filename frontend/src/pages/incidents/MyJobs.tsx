import { Badge, Button, Group, Paper, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { DutyStatus, Job, JobsData } from '@/api/types'
import { JobPlan } from '../jobs/JobPlan'
import { ErrorBanner } from '@bitsandbricks/ui'
import { clock } from '@/lib/time'
import { incidentTitle } from '@/lib/incidentTitle'
import { toastDone } from '@bitsandbricks/ui'

function since(ts: number) {
  return clock(ts)
}

function JobCard({ job, busy, onAnswer }: { job: Job; busy: boolean; onAnswer: (kind: 'take' | 'done' | 'give-back', note: string) => void }) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')
  const where = job.seat ? t('incidents.seat', { seat: job.seat })
    : job.circuit_id ? t('incidents.circuit', { name: job.circuit_name ?? job.circuit_id })
    : t('incidents.switch', { name: job.switch_name ?? job.switch_id })
  const last = job.notes[job.notes.length - 1]
  return (
    <Paper withBorder radius="lg" p="sm" component="article" aria-label={job.title}>
      <Stack gap={8}>
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Title order={2} size="h4" style={{ overflowWrap: 'anywhere' }}>{incidentTitle(job.title, t)}</Title>
          {job.dispatched_at && <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('jobs.sent', { when: since(job.dispatched_at) })}</Text>}
        </Group>
        <Group gap={6}>
          <Badge variant="light" color="trace" tt="none" size="lg">{where}</Badge>
          {job.hall && <Badge variant="outline" tt="none">{t('jobs.otherHall', { hall: job.hall })}</Badge>}
          {job.source === 'helpdesk' && <Badge variant="light" color="bit" tt="none">{t('incidents.fromSeat')}</Badge>}
          {job.taken_at && <Badge variant="light" color="up" tt="none">{t('jobs.taken', { when: since(job.taken_at) })}</Badge>}
        </Group>
        {/* Before the walk: the seat may have fixed itself (issue #382). */}
        {job.seat_ok_at && (
          <Text size="sm" fw={600} c="up" data-seat-ok>{t('jobs.seatOk', { when: since(job.seat_ok_at) })}</Text>
        )}
        {last && <Text size="sm">“{last.text}”</Text>}
        {job.drawing && job.target ? (
          <>
            <JobPlan job={job} label={t('jobs.planLabel', { where })} you={t('jobs.you')} />
            {job.from && <Text size="xs" c="dimmed">{t('jobs.routeHelp')}</Text>}
          </>
        ) : <Text size="sm" c="dimmed">{t('jobs.noPlace')}</Text>}
        <TextInput aria-label={t('jobs.note')} placeholder={t('jobs.note')} value={note} maxLength={2000}
          onChange={(e) => setNote(e.currentTarget.value)} />
        <Stack gap="xs">
          {!job.taken_at && <Button size="md" fullWidth loading={busy} onClick={() => onAnswer('take', '')}>{t('jobs.onMyWay')}</Button>}
          <Button size="md" fullWidth color="up" variant={job.taken_at ? 'filled' : 'light'} loading={busy} onClick={() => onAnswer('done', note.trim())}>
            {t('jobs.done')}
          </Button>
          <Button size="md" fullWidth variant="default" loading={busy} onClick={() => onAnswer('give-back', note.trim())}>{t('jobs.giveBack')}</Button>
        </Stack>
      </Stack>
    </Paper>
  )
}

/** The tech's side of the incident board (issue #887, was My jobs): on duty or not, where they
 *  are, and the incidents sent to them, above the board. */
export function MyJobs() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const jobs = useQuery({ queryKey: qk.jobs, queryFn: () => get<JobsData>('/api/jobs'), refetchInterval: 15_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.jobs })
  useLiveEvent('incident.changed', refresh)
  const duty = useMutation({
    mutationFn: (body: Partial<DutyStatus>) => put<DutyStatus>('/api/jobs/me', body),
    onSuccess: refresh,
  })
  const answer = useMutation({
    mutationFn: (v: { id: string; kind: 'take' | 'done' | 'give-back'; note: string }) => post(`/api/jobs/${v.id}/${v.kind}`, { note: v.note }),
    onSuccess: (_r, v) => {
      if (v.kind !== 'take') toastDone(v.kind === 'done' ? t('jobs.doneMsg') : t('jobs.backMsg'))
      refresh()
    },
  })
  const data = jobs.data
  const error = jobs.error ?? duty.error ?? answer.error
  if (!data) return <ErrorBanner error={error} mb="md" />
  return (
    <Stack gap="sm" mb="md">
      <ErrorBanner error={error} />
      <Paper withBorder radius="lg" p="sm" role="group" aria-label={t('jobs.title')}>
        <Group gap="lg" align="flex-end" wrap="wrap">
          <Switch size="md" label={t('jobs.onDuty')} description={t('jobs.onDutyHelp')} checked={data.me.on_duty}
            onChange={(e) => duty.mutate({ on_duty: e.currentTarget.checked })} />
          <Select w={220} label={t('jobs.whereAmI')} placeholder={t('jobs.pickSeat')} searchable clearable
            data={data.seats} value={data.me.at && data.seats.includes(data.me.at) ? data.me.at : null}
            onChange={(v) => duty.mutate({ at: v ?? '' })} limit={50} />
          <Text size="sm" c="dimmed" style={{ flex: '1 1 16em' }}>
            {!data.me.on_duty ? t('jobs.offDuty') : data.auto ? t('jobs.autoOn') : t('jobs.whereHelp')}
          </Text>
          {(data.done ?? 0) > 0 && <Text size="sm" c="up" role="status">{t('jobs.doneLately', { count: data.done })}</Text>}
        </Group>
      </Paper>
      {data.jobs.length > 0 && (
        <section aria-labelledby="fb-jobs-sent">
          <Title order={2} size="h4" id="fb-jobs-sent" mb="xs">{t('jobs.sentToYou', { count: data.jobs.length })}</Title>
          <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
            {data.jobs.map((job) => (
              <JobCard key={job.id} job={job} busy={answer.isPending && answer.variables?.id === job.id}
                onAnswer={(kind, note) => answer.mutate({ id: job.id, kind, note })} />
            ))}
          </SimpleGrid>
        </section>
      )}
    </Stack>
  )
}
