import { Anchor, Button, Group, Select, SimpleGrid, Stack, Text, Textarea } from '@mantine/core'
import { IconArrowLeft } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useIncidentPeople, useIncidents, useMe } from '@/api/queries'
import type { CrewMember, Incident } from '@/api/types'
import { BouncePort } from '@/components/BouncePort'
import { Layout } from '@/components/Layout'
import { Field, Panel } from '@/components/ui'
import { useNowSeconds } from '@/components/useNowSeconds'
import { incidentTitle, powerNote } from '@/lib/incidentTitle'
import { ago, dateTime } from '@/lib/time'
import { EmptyState, ErrorBanner, LoadingState, PageHead } from '@bitsandbricks/ui'
import type { IncidentChange } from './IncidentCard'
import { IncidentBadges, IncidentDetails, OwnerLine } from './IncidentFacts'
import { whereOf } from './where'

/** One incident on its own page (issue #887): everything the board's card leaves out. What was
 *  known when it came in, who has it, every note, and every action this account may take. */
export default function IncidentPage() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const client = useQueryClient()
  const board = useIncidents()
  const people = useIncidentPeople()
  const me = useMe()
  const now = useNowSeconds()
  const [note, setNote] = useState('')
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const crew = useQuery({
    queryKey: qk.crew, queryFn: () => get<{ crew: CrewMember[]; auto?: boolean }>('/api/dispatch/crew'),
    enabled: !!board.data?.can_assign_any, refetchInterval: 30_000,
  })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: qk.incidents })
    void client.invalidateQueries({ queryKey: qk.crew })
  }
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('dispatch.changed', refresh)
  const change = useMutation({
    mutationFn: (c: IncidentChange) => patch<Incident>(`/api/incidents/${encodeURIComponent(id)}`, c),
    onSuccess: () => { setMessage(null); refresh() },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const send = useMutation({
    mutationFn: () => post<{ display_name: string }>(`/api/incidents/${encodeURIComponent(id)}/dispatch`),
    onSuccess: (r) => { refresh(); setMessage({ ok: true, text: t('incidents.sentTo', { name: r.display_name }) }) },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const back = (
    <Anchor component={Link} to="/incidents" size="sm"><IconArrowLeft size={14} style={{ verticalAlign: -2 }} /> {t('incident.back')}</Anchor>
  )

  if (board.isPending) return <Layout title={t('incidents.title')}><LoadingState /></Layout>
  const i = board.data?.incidents.find((x) => x.id === id)
  if (!board.data || !i) {
    return (
      <Layout title={t('incidents.title')}>
        <PageHead title={t('incident.title')} back={back} />
        {board.data ? <EmptyState title={t('incident.gone')} description={t('incident.goneDesc')} /> : <ErrorBanner error={board.error} />}
      </Layout>
    )
  }
  const data = board.data
  const username = me.data?.user?.username
  const busy = change.isPending || send.isPending
  const assignable = (people.data?.[i.team ?? ''] ?? []).map((p) => ({ value: p.username, label: p.display_name }))
  const title = incidentTitle(i.title, t)
  const addNote = () => {
    if (!note.trim()) return
    change.mutate({ note: note.trim() }, { onSuccess: () => setNote('') })
  }

  return (
    <Layout title={title}>
      <PageHead back={back} title={title}
        // One line: on wide screens the top bar shows the title and only the eyebrow stays.
        eyebrow={<>{t(`incidents.status.${i.status}`)} · {whereOf(i, t)} · {t('incident.filed', { ago: ago(i.created_at), at: dateTime(i.created_at) })}</>}
        actions={i.can_work && (
          <Group gap="xs">
            {i.status === 'open' && (
              <Button loading={busy} onClick={() => change.mutate({ status: 'assigned', assignee: username ?? null })}>{t('incidents.take')}</Button>
            )}
            {i.status !== 'fixed' && (
              <Button variant="default" loading={busy} onClick={() => change.mutate({ status: 'fixed' })}>{t('incidents.fixed')}</Button>
            )}
            {i.status === 'fixed' && (
              <Button variant="default" loading={busy} onClick={() => change.mutate({ status: 'open' })}>{t('incidents.reopen')}</Button>
            )}
          </Group>
        )} />
      <Stack gap="md">
        {message && (
          <Text size="sm" role="status" className={message.ok ? 'fb-tone-ok' : 'fb-tone-err'}>{message.text}</Text>
        )}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          <Panel title={t('incident.what')}>
            <Stack gap="sm">
              <IncidentBadges i={i} board={data} now={now} full />
              <IncidentDetails i={i} />
              {/* The usual first try for a seat without internet; what it did goes in the notes. */}
              {i.seat && i.can_work && i.status !== 'fixed' && (
                <Group><BouncePort seat={i.seat} onBounced={(text) => change.mutate({ note: text })} /></Group>
              )}
            </Stack>
          </Panel>
          <Panel title={t('incident.who')}>
            <Stack gap="sm">
              <OwnerLine i={i} now={now} />
              {i.can_assign && i.status === 'open' && !i.assignee && (
                <Group>
                  <Button variant="light" loading={send.isPending} disabled={!crew.data?.crew.length}
                    title={crew.data?.crew.length ? undefined : t('incidents.crewNone')} onClick={() => send.mutate()}>
                    {t('incidents.sendNearest')}
                  </Button>
                </Group>
              )}
              {i.can_assign && i.status !== 'fixed' && (
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  <Select label={t('incidents.assignee')} placeholder={t('incidents.unassigned')} data={assignable}
                    value={i.assignee} clearable disabled={busy} onChange={(v) => change.mutate({ assignee: v })} />
                  <Select label={t('incidents.team')} placeholder={t('incidents.noTeam')} disabled={busy}
                    data={data.teams.filter((x) => data.assign_teams.includes(x.id)).map((x) => ({ value: x.id, label: x.name }))}
                    value={i.team} onChange={(v) => v && change.mutate({ team: v })} />
                </SimpleGrid>
              )}
              {i.dispatched_at && (
                <Field label={t('incident.sent')}>
                  <Text size="sm">{dateTime(i.dispatched_at)}{i.taken_at ? ` · ${t('incident.takenAt', { at: dateTime(i.taken_at) })}` : ''}</Text>
                </Field>
              )}
              {i.fixed_at && <Field label={t('incident.fixedAt')}><Text size="sm">{dateTime(i.fixed_at)}</Text></Field>}
            </Stack>
          </Panel>
        </SimpleGrid>
        <Panel title={t('incident.notes', { count: i.notes.length })}>
          <Stack gap="sm">
            {!i.notes.length && <Text size="sm" c="dimmed">{t('incident.noNotes')}</Text>}
            {i.notes.map((n, k) => (
              <div key={`${n.at}-${k}`} data-note>
                <Text size="sm" style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
                  {!n.by && i.source === 'power' ? powerNote(n.text, t) : n.text}
                </Text>
                <Text size="xs" c="dimmed">
                  {n.by ?? (i.source === 'power' ? 'Floorbit' : t('incidents.attendee'))} · {ago(n.at)}
                </Text>
              </div>
            ))}
            {i.can_work && (
              <Group align="flex-end" gap="xs">
                <Textarea label={t('incidents.addNote')} value={note} maxLength={2000} autosize minRows={1} style={{ flex: 1 }}
                  onChange={(e) => setNote(e.currentTarget.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); addNote() } }} />
                <Button variant="default" disabled={!note.trim()} loading={change.isPending && !!change.variables?.note} onClick={addNote}>
                  {t('incident.addNote')}
                </Button>
              </Group>
            )}
          </Stack>
        </Panel>
      </Stack>
    </Layout>
  )
}
