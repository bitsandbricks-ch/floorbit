import { Alert, Badge, Button, Group, Loader, Paper, Select, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { DutyStatus, Job, JobsData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { JobPlan } from './jobs/JobPlan'

function since(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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
          <Title order={2} size="h4" style={{ overflowWrap: 'anywhere' }}>{job.title}</Title>
          {job.dispatched_at && <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('jobs.sent', { when: since(job.dispatched_at) })}</Text>}
        </Group>
        <Group gap={6}>
          <Badge variant="light" color="trace" tt="none" size="lg">{where}</Badge>
          {job.hall && <Badge variant="outline" tt="none">{t('jobs.otherHall', { hall: job.hall })}</Badge>}
          {job.source === 'helpdesk' && <Badge variant="light" color="bit" tt="none">{t('incidents.fromSeat')}</Badge>}
          {job.taken_at && <Badge variant="light" color="up" tt="none">{t('jobs.taken', { when: since(job.taken_at) })}</Badge>}
        </Group>
        {last && <Text size="sm">“{last.text}”</Text>}
        {job.drawing && job.target ? (
          <>
            <JobPlan job={job} label={t('jobs.planLabel', { where })} you={t('jobs.you')} />
            {job.from && <Text size="xs" c="dimmed">{t('jobs.routeHelp')}</Text>}
          </>
        ) : <Text size="sm" c="dimmed">{t('jobs.noPlace')}</Text>}
        <TextInput aria-label={t('jobs.note')} placeholder={t('jobs.note')} value={note} maxLength={2000}
          onChange={(e) => setNote(e.currentTarget.value)} />
        <Group gap="xs" grow>
          {!job.taken_at && <Button size="md" loading={busy} onClick={() => onAnswer('take', '')}>{t('jobs.onMyWay')}</Button>}
          <Button size="md" color="up" variant={job.taken_at ? 'filled' : 'light'} loading={busy} onClick={() => onAnswer('done', note.trim())}>
            {t('jobs.done')}
          </Button>
          <Button size="md" variant="default" loading={busy} onClick={() => onAnswer('give-back', note.trim())}>{t('jobs.giveBack')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

/** The tech's phone: on duty or not, where they are, and the jobs sent to them. */
export default function Jobs() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const jobs = useQuery({ queryKey: qk.jobs, queryFn: () => get<JobsData>('/api/jobs'), refetchInterval: 15_000 })
  const [message, setMessage] = useState<string | null>(null)
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.jobs })
  useLiveEvent('incident.changed', refresh)
  const duty = useMutation({
    mutationFn: (body: Partial<DutyStatus>) => put<DutyStatus>('/api/jobs/me', body),
    onSuccess: refresh,
  })
  const answer = useMutation({
    mutationFn: (v: { id: string; kind: 'take' | 'done' | 'give-back'; note: string }) => post(`/api/jobs/${v.id}/${v.kind}`, { note: v.note }),
    onSuccess: (_r, v) => {
      setMessage(v.kind === 'done' ? t('jobs.doneMsg') : v.kind === 'give-back' ? t('jobs.backMsg') : null)
      refresh()
    },
  })
  const data = jobs.data
  const error = jobs.error ?? duty.error ?? answer.error

  return (
    <Layout title={t('jobs.title')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <PageHead title={t('jobs.title')} desc={t('jobs.intro')} />
      <Stack gap="md">
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {message && <Alert color="up" role="status" withCloseButton onClose={() => setMessage(null)}>{message}</Alert>}
        {jobs.isPending ? <Loader aria-label={t('common.loading')} /> : data && (
          <>
            <Paper withBorder radius="lg" p="sm">
              <Stack gap="sm">
                <Switch size="md" label={t('jobs.onDuty')} description={t('jobs.onDutyHelp')} checked={data.me.on_duty}
                  onChange={(e) => duty.mutate({ on_duty: e.currentTarget.checked })} />
                <Select label={t('jobs.whereAmI')} description={t('jobs.whereHelp')} placeholder={t('jobs.pickSeat')} searchable clearable
                  data={data.seats} value={data.me.at && data.seats.includes(data.me.at) ? data.me.at : null}
                  onChange={(v) => duty.mutate({ at: v ?? '' })} limit={50} />
              </Stack>
            </Paper>
            {!data.me.on_duty && <Text size="sm" c="dimmed">{t('jobs.offDuty')}</Text>}
            {data.jobs.length === 0 ? (
              <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('jobs.none')}</Text></Paper>
            ) : data.jobs.map((job) => (
              <JobCard key={job.id} job={job} busy={answer.isPending && answer.variables?.id === job.id}
                onAnswer={(kind, note) => answer.mutate({ id: job.id, kind, note })} />
            ))}
          </>
        )}
      </Stack>
    </Layout>
  )
}
