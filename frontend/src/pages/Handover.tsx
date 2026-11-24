import { Alert, Anchor, Badge, Button, CopyButton, Group, Paper, SimpleGrid, Stack, Switch, Text, Textarea, Title } from '@mantine/core'
import { IconCheck, IconCopy } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { HandoverData, HandoverIncident, HandoverRecord } from '@/api/types'
import { DataTable, LoadingState, PageHead, StatTile } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { duration } from './report/format'
import { byLine, summaryText, when } from './handover/format'
import { isWaiting, waitedFor } from './incidents/waiting'
import { incidentTitle } from '@/lib/incidentTitle'

/** A count that only takes its colour when there is something to count. */
function Figure({ label, value, tone, sub }: { label: string; value: number; tone?: 'err' | 'warn' | 'ok'; sub?: string }) {
  return <StatTile label={label} value={String(value)} tone={tone && value > 0 ? tone : undefined} sub={sub} />
}

/** The open or fixed incidents as one table: one status badge in its own column, and the wait as
 *  plain text that only turns amber once nobody has picked the job up for a while (issue #888). */
function IncidentTable({ rows, now, fixed }: { rows: HandoverIncident[]; now: number; fixed?: boolean }) {
  const { t } = useTranslation()
  const where = (i: HandoverIncident) => i.where.kind === 'seat' ? t('incidents.seat', { seat: i.where.name })
    : i.where.kind === 'circuit' ? t('incidents.circuit', { name: i.where.name }) : t('incidents.switch', { name: i.where.name })
  return (
    <DataTable rows={rows} rowKey={(i) => i.id} label={fixed ? t('handover.fixedThisShift') : t('handover.stillOpen')}
      urlState={false} pageSize={25} bare cards density="compact"
      columns={[
        { id: 'what', header: t('handover.colIncident'), wrap: true, cell: (i) => (
          <>
            <Text fw={600} size="sm" style={{ overflowWrap: 'anywhere' }}>{incidentTitle(i.title, t)}</Text>
            <Text size="xs" c="dimmed">{where(i)}</Text>
          </>
        ) },
        { id: 'who', header: t('handover.who'), card: 'label', cell: (i) => i.assignee ?? '–' },
        { id: 'age', header: fixed ? t('handover.colTook') : t('handover.colAge'), card: 'label', cell: (i) => fixed && i.fixed_at
          ? duration(Math.max(60, i.fixed_at - i.created_at))
          : isWaiting(i, now) ? <Text span size="sm" c="warn" fw={600}>{waitedFor(now - i.created_at, t)}</Text>
            : duration(Math.max(60, now - i.created_at)) },
        { id: 'status', header: t('handover.colStatus'), card: 'actions', width: 110, cell: (i) => (
          <Badge variant="light" color={i.status === 'fixed' ? 'up' : 'gray'} tt="none">{t(`handover.status.${i.status}`)}</Badge>
        ) },
      ]} />
  )
}

function Note({ record, title }: { record: HandoverRecord; title: string }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" bg="var(--color-raised)">
      <Text size="sm" fw={600} mb={4}>{title}</Text>
      <Text size="xs" c="dimmed" mb={6}>{t('handover.by', { who: record.by ?? '?', when: when(record.at) })}</Text>
      <Text style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{record.note || t('handover.noNote')}</Text>
    </Paper>
  )
}

/** What the next shift needs to know, and a note from the one going off. */
export default function Handover() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.handover, queryFn: () => get<HandoverData>('/api/handover'), refetchInterval: 60_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.handover })
  useLiveEvent('incident.changed', refresh)
  useLiveEvent('handover.changed', refresh)
  const [note, setNote] = useState('')
  const [discord, setDiscord] = useState(true)
  const [done, setDone] = useState<HandoverRecord & { posted: boolean | null } | null>(null)
  const send = useMutation({
    mutationFn: () => post<HandoverRecord & { posted: boolean | null }>('/api/handover', { note: note.trim(), discord }),
    onSuccess: (r) => { setDone(r); setNote(''); refresh() },
  })
  const d = query.data

  return (
    <Layout title={t('handover.title')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <PageHead title={t('handover.title')} desc={t('handover.intro')} actions={d && (
        <CopyButton value={summaryText(d, note, t, duration)} timeout={2000}>
          {({ copied, copy }) => (
            <Button variant="default" leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              color={copied ? 'up' : undefined} onClick={copy}>
              {copied ? t('handover.copied') : t('handover.copy')}
            </Button>
          )}
        </CopyButton>
      )} />
      <Stack gap="md">
        {(query.error ?? send.error) && <Alert color="down" role="alert">{t('common.error', { message: (query.error ?? send.error)!.message })}</Alert>}
        {done && (
          <Alert color="up" role="status" withCloseButton onClose={() => setDone(null)}>
            {done.posted ? t('handover.doneDiscord') : t('handover.done')}
          </Alert>
        )}
        {query.isPending ? <LoadingState rows={3} /> : d && (
          <>
            <Text size="sm" c="dimmed">{t('handover.since', { when: when(d.since) })}</Text>
            {d.previous && <Note record={d.previous} title={t('handover.lastNote')} />}
            {d.notice && (
              <Alert color={d.notice.level === 'warn' ? 'warn' : 'gray'} variant="light" title={t('handover.noticeUp')}>
                {d.notice.text}{d.notice.by ? ` (${t('handover.noticeBy', { who: d.notice.by })})` : ''}
              </Alert>
            )}
            <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
              <Figure label={t('handover.open')} value={d.counts.open} tone="err"
                sub={d.counts.waiting ? t('handover.waiting', { count: d.counts.waiting }) : undefined} />
              <Figure label={t('handover.opened')} value={d.counts.opened} />
              <Figure label={t('handover.fixed')} value={d.counts.fixed}
                sub={d.counts.median_fix_s != null ? t('handover.halfWithin', { d: duration(Math.max(60, d.counts.median_fix_s)) }) : undefined} />
              <Figure label={t('handover.outages')} value={d.counts.outages} tone="warn" />
              <Figure label={t('handover.problems')} value={d.counts.problems} tone="warn" />
              <Figure label={t('handover.changes')} value={d.counts.changes} />
            </SimpleGrid>

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('handover.stillOpen')}</Title>
              {d.incidents.open.length === 0 ? <Text size="sm" c="dimmed">{t('handover.noneOpen')}</Text> : (
                <IncidentTable rows={d.incidents.open} now={d.now} />
              )}
            </Paper>

            {d.incidents.fixed.length > 0 && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('handover.fixedThisShift')}</Title>
                <Text size="sm" c="dimmed" mb="xs">
                  {byLine(d.incidents.fixed, t)}
                </Text>
                <IncidentTable rows={d.incidents.fixed} now={d.now} fixed />
              </Paper>
            )}

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('handover.outagesTitle')}</Title>
              {d.outages.length === 0 ? <Text size="sm" c="dimmed">{t('handover.noOutages')}</Text> : (
                <Stack gap={6}>
                  {d.outages.map((o) => (
                    <Group key={`${o.switch_id}-${o.down_at}`} justify="space-between" wrap="nowrap">
                      <Text fw={600}>{o.name}</Text>
                      <Text size="sm" c={o.back_at ? 'dimmed' : 'down'}>
                        {o.back_at ? t('handover.wasDown', { when: when(o.down_at), for: duration(o.down_s) })
                          : t('handover.stillDown', { when: when(o.down_at), for: duration(o.down_s) })}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('handover.changesTitle')}</Title>
              {d.changes.length === 0 ? <Text size="sm" c="dimmed">{t('handover.noChanges')}</Text> : (
                <DataTable rows={d.changes} rowKey={(_, n) => String(n)} label={t('handover.changesTitle')} urlState={false} pageSize={25}
                  bare striped cards density="compact"
                  columns={[
                    { id: 'when', header: t('handover.when'), card: 'inline', cell: (c) => when(c.at) },
                    { id: 'who', header: t('handover.who'), card: 'inline', cell: (c) => c.user ?? '–' },
                    { id: 'what', header: t('handover.what'), wrap: true, cell: (c) => `${c.action}${c.target ? `: ${c.target}` : ''}` },
                  ]} />
              )}
            </Paper>

            {!!d.mutes?.length && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('handover.mutedTitle')}</Title>
                <Stack gap={6}>
                  {d.mutes.map((m) => (
                    <Group key={`${m.kind}-${m.name}`} gap="sm" wrap="nowrap" align="baseline">
                      <Anchor href={m.kind === 'health' ? '/services' : `/plan?switch=${encodeURIComponent(m.name)}`} fw={600} style={{ whiteSpace: 'nowrap' }}>{m.name}</Anchor>
                      <Text size="sm" style={{ flex: 1, overflowWrap: 'anywhere' }}>
                        {t('handover.mutedUntil', { until: when(m.until), who: m.by ?? '?' })}{m.reason ? ` · ${m.reason}` : ''}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              </Paper>
            )}

            {!!d.coming_up?.length && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('handover.comingUp')}</Title>
                <Stack gap={6}>
                  {d.coming_up.map((i) => (
                    <Group key={i.id} gap="sm" wrap="nowrap" align="baseline">
                      <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{when(i.start)}</Text>
                      <Text size="sm" fw={600} style={{ flex: 1, overflowWrap: 'anywhere' }}>
                        {i.title}{i.where ? <Text span size="sm" fw={400} c="dimmed"> · {i.where}</Text> : null}
                      </Text>
                      {i.kind === 'tournament' && <Badge size="sm" variant="light" color="warn">{t('handover.tournament')}</Badge>}
                    </Group>
                  ))}
                </Stack>
                <Anchor href="/schedule" size="sm" mt="xs" display="inline-block">{t('handover.fullSchedule')}</Anchor>
              </Paper>
            )}

            {d.seat_notes.length > 0 && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('handover.seatNotes')}</Title>
                <Stack gap={6}>
                  {d.seat_notes.map((n) => (
                    <Group key={n.seat} gap="sm" wrap="nowrap" align="baseline">
                      <Anchor href={`/plan?seat=${encodeURIComponent(n.seat)}`} fw={600} style={{ whiteSpace: 'nowrap' }}>{n.seat}</Anchor>
                      <Text size="sm" style={{ flex: 1, overflowWrap: 'anywhere' }}>{n.text}</Text>
                      <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{n.by ? `${n.by} · ` : ''}{when(n.at)}</Text>
                    </Group>
                  ))}
                </Stack>
              </Paper>
            )}

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('handover.handOver')}</Title>
              <Stack gap="sm">
                <Textarea label={t('handover.note')} description={t('handover.noteHelp')} value={note} maxLength={4000}
                  autosize minRows={3} onChange={(e) => setNote(e.currentTarget.value)} />
                {d.discord && <Switch label={t('handover.toDiscord')} checked={discord} onChange={(e) => setDiscord(e.currentTarget.checked)} />}
                <Group justify="flex-end">
                  <Button loading={send.isPending} onClick={() => send.mutate()}>{t('handover.handOver')}</Button>
                </Group>
              </Stack>
            </Paper>

            {d.history.length > 1 && (
              <Stack gap="sm">
                <Title order={2} size="h4">{t('handover.earlier')}</Title>
                {d.history.slice(1).map((h) => <Note key={h.id} record={h} title={t('handover.counts', { ...h.counts })} />)}
              </Stack>
            )}
          </>
        )}
      </Stack>
    </Layout>
  )
}
