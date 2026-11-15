import {
  ActionIcon, Alert, Badge, Button, Group, Loader, Modal, Paper, Progress, Stack, Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconDownload, IconPencil } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { EventFigures, EventsData, PastEvent } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { dates, METRICS, share } from './events/metrics'

type Column = { id: string; name: string; start: number | null; end: number | null; figures: EventFigures; current?: boolean }

function Comparison({ columns }: { columns: Column[] }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{t('events.compare')}</Title>
      <Table.ScrollContainer minWidth={180 + columns.length * 150}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th />
              {columns.map((c) => (
                <Table.Th key={c.id}>
                  <Text fw={700} size="sm">{c.name || t('events.unnamed')}</Text>
                  <Group gap={6}>
                    <Text size="xs" c="dimmed">{dates(c.start, c.end)}</Text>
                    {c.current && <Badge size="xs" variant="light" color="up" tt="none">{t('events.running')}</Badge>}
                  </Group>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {METRICS.map((m) => {
              const values = columns.map((c) => c.figures[m.key])
              return (
                <Table.Tr key={m.key}>
                  <Table.Td><Text size="sm">{t(`events.metric.${m.key}`)}</Text></Table.Td>
                  {columns.map((c) => {
                    const v = c.figures[m.key]
                    return (
                      <Table.Td key={c.id}>
                        <Text fw={600} size="sm">{v === null ? '–' : m.format(v)}</Text>
                        <Progress value={share(v, values)} size="xs" color={c.current ? 'up' : 'trace'}
                          aria-label={t(`events.metric.${m.key}`)} />
                      </Table.Td>
                    )
                  })}
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" mt="xs">{t('events.cacheNote')}</Text>
    </Paper>
  )
}

function RenameModal({ event, onClose, onDone }: { event: PastEvent; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState(event.name)
  const save = useMutation({ mutationFn: () => patch(`/api/past-events/${event.id}`, { name: name.trim() }), onSuccess: onDone })
  return (
    <Modal opened onClose={onClose} title={t('events.rename')} centered>
      <Stack gap="sm">
        <TextInput label={t('events.name')} value={name} maxLength={120} onChange={(e) => setName(e.currentTarget.value)} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('events.save')}</Button>
      </Stack>
    </Modal>
  )
}

function CloseEvent({ name, onDone }: { name: string; onDone: (archived: PastEvent) => void }) {
  const { t } = useTranslation()
  const [confirm, setConfirm] = useState('')
  const [next, setNext] = useState('')
  const word = name || 'close'
  const close = useMutation({
    mutationFn: () => post<{ archived: PastEvent }>('/api/past-events/close', { confirm, next_name: next.trim() }),
    onSuccess: (r) => { setConfirm(''); setNext(''); onDone(r.archived) },
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb={4}>{t('events.closeTitle')}</Title>
      <Text size="sm" c="dimmed" mb="sm">{t('events.closeHelp')}</Text>
      <Stack gap="sm">
        <TextInput label={t('events.nextName')} description={t('events.nextNameHelp')} value={next} maxLength={120}
          onChange={(e) => setNext(e.currentTarget.value)} />
        <TextInput label={t('events.typeToConfirm', { word })} value={confirm} onChange={(e) => setConfirm(e.currentTarget.value)} />
        {close.error && <Alert color="down" role="alert">{close.error.message}</Alert>}
        <Group justify="flex-end">
          <Button color="down" loading={close.isPending} disabled={confirm.trim().toLowerCase() !== word.toLowerCase()}
            onClick={() => close.mutate()}>
            {t('events.close')}
          </Button>
        </Group>
      </Stack>
    </Paper>
  )
}

/** Every event as its own record, and how they compare. */
export default function Events() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const isAdmin = useCan('settings.manage')
  const query = useQuery({ queryKey: qk.events, queryFn: () => get<EventsData>('/api/past-events') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.events })
  useLiveEvent('events.changed', refresh)
  const [renaming, setRenaming] = useState<PastEvent | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/past-events/${id}`), onSuccess: refresh })
  const d = query.data
  const tz = new Date().getTimezoneOffset()
  const lang = i18n.language.startsWith('de') ? 'de' : 'en'
  const columns: Column[] = d ? [{ id: 'current', ...d.current, current: true }, ...d.archived] : []
  const error = query.error ?? remove.error

  return (
    <Layout title={t('events.title')} back={{ href: '/report', label: t('report.title') }}>
      <PageHead title={t('events.title')} desc={t('events.intro')} />
      <Stack gap="md">
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {notice && <Alert color="up" role="status" withCloseButton onClose={() => setNotice(null)}>{notice}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            <Comparison columns={columns} />
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('events.past')}</Title>
              {d.archived.length === 0 ? <Text size="sm" c="dimmed">{t('events.none')}</Text> : (
                <Stack gap="sm">
                  {d.archived.map((e) => (
                    <Group key={e.id} justify="space-between" wrap="wrap" gap="xs">
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Group gap={4} wrap="nowrap">
                          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{e.name}</Text>
                          {isAdmin && (
                            <ActionIcon variant="subtle" size="sm" aria-label={t('events.rename')} onClick={() => setRenaming(e)}>
                              <IconPencil size={14} />
                            </ActionIcon>
                          )}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {dates(e.start, e.end)} · {t('events.closedBy', { who: e.archived_by ?? '?' })}
                        </Text>
                      </Stack>
                      <Group gap="xs">
                        <Button size="compact-sm" variant="default" component="a" leftSection={<IconDownload size={14} />}
                          href={`/api/past-events/${e.id}/report.pdf?lang=${lang}&tz=${tz}`}>
                          {t('events.report')}
                        </Button>
                        {isAdmin && (
                          <>
                            <Button size="compact-sm" variant="default" component="a" leftSection={<IconDownload size={14} />}
                              href={`/api/past-events/backup/${e.id}.json`}>
                              {t('events.floorPlan')}
                            </Button>
                            <ConfirmButton size="compact-sm" variant="default" danger label={t('events.delete')}
                              question={t('events.deleteQuestion', { name: e.name })} onConfirm={() => remove.mutate(e.id)} />
                          </>
                        )}
                      </Group>
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>
            {isAdmin && (
              <CloseEvent name={d.current.name} onDone={(a) => { setNotice(t('events.closed', { name: a.name })); refresh() }} />
            )}
          </>
        )}
      </Stack>
      {renaming && <RenameModal event={renaming} onClose={() => setRenaming(null)} onDone={() => { setRenaming(null); refresh() }} />}
    </Layout>
  )
}
