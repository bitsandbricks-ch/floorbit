import { Alert, Badge, Button, Group, Loader, Paper, SimpleGrid, Stack, Switch, Table, Text, Textarea, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { HandoverData, HandoverIncident, HandoverRecord } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { duration } from './report/format'
import { when } from './handover/format'

function Figure({ label, value, tone }: { label: string; value: number; tone?: 'down' | 'warn' | 'up' }) {
  return (
    <Paper withBorder radius="lg" p="sm">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fz={28} fw={700} c={tone && value > 0 ? tone : undefined}>{value}</Text>
    </Paper>
  )
}

function IncidentRow({ i }: { i: HandoverIncident }) {
  const { t } = useTranslation()
  const where = i.where.kind === 'seat' ? t('incidents.seat', { seat: i.where.name })
    : i.where.kind === 'circuit' ? t('incidents.circuit', { name: i.where.name }) : t('incidents.switch', { name: i.where.name })
  return (
    <Group justify="space-between" wrap="nowrap" align="flex-start">
      <Stack gap={2} style={{ minWidth: 0 }}>
        <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{i.title}</Text>
        <Text size="sm" c="dimmed">{where}{i.assignee ? ` · ${i.assignee}` : ''}</Text>
      </Stack>
      <Group gap={4} wrap="nowrap">
        {i.match && <Badge variant="light" color="warn" tt="none">{i.match}</Badge>}
        <Badge variant="light" color={i.status === 'open' ? 'down' : i.status === 'fixed' ? 'up' : 'trace'} tt="none">
          {t(`handover.status.${i.status}`)}
        </Badge>
      </Group>
    </Group>
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
      <PageHead title={t('handover.title')} desc={t('handover.intro')} />
      <Stack gap="md">
        {(query.error ?? send.error) && <Alert color="down" role="alert">{t('common.error', { message: (query.error ?? send.error)!.message })}</Alert>}
        {done && (
          <Alert color="up" role="status" withCloseButton onClose={() => setDone(null)}>
            {done.posted ? t('handover.doneDiscord') : t('handover.done')}
          </Alert>
        )}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            <Text size="sm" c="dimmed">{t('handover.since', { when: when(d.since) })}</Text>
            {d.previous && <Note record={d.previous} title={t('handover.lastNote')} />}
            <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
              <Figure label={t('handover.open')} value={d.counts.open} tone="down" />
              <Figure label={t('handover.opened')} value={d.counts.opened} />
              <Figure label={t('handover.fixed')} value={d.counts.fixed} tone="up" />
              <Figure label={t('handover.outages')} value={d.counts.outages} tone="warn" />
              <Figure label={t('handover.problems')} value={d.counts.problems} tone="warn" />
              <Figure label={t('handover.changes')} value={d.counts.changes} />
            </SimpleGrid>

            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('handover.stillOpen')}</Title>
              {d.incidents.open.length === 0 ? <Text size="sm" c="dimmed">{t('handover.noneOpen')}</Text> : (
                <Stack gap="sm">{d.incidents.open.map((i) => <IncidentRow key={i.id} i={i} />)}</Stack>
              )}
            </Paper>

            {d.incidents.fixed.length > 0 && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('handover.fixedThisShift')}</Title>
                <Stack gap="sm">{d.incidents.fixed.map((i) => <IncidentRow key={i.id} i={i} />)}</Stack>
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
                <Table.ScrollContainer minWidth={520}>
                  <Table striped>
                    <Table.Thead>
                      <Table.Tr><Table.Th>{t('handover.when')}</Table.Th><Table.Th>{t('handover.who')}</Table.Th><Table.Th>{t('handover.what')}</Table.Th></Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {d.changes.map((c, n) => (
                        <Table.Tr key={n}>
                          <Table.Td style={{ whiteSpace: 'nowrap' }}>{when(c.at)}</Table.Td>
                          <Table.Td>{c.user ?? '–'}</Table.Td>
                          <Table.Td>{c.action}{c.target ? `: ${c.target}` : ''}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </Paper>

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
