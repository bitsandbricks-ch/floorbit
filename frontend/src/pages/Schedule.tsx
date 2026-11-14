import {
  ActionIcon, Alert, Anchor, Badge, Button, FileButton, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Text,
  TextInput, Title,
} from '@mantine/core'
import { IconCalendarPlus, IconPencil, IconPlus, IconTrash, IconUpload } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { ScheduleData, ScheduleItem, ScheduleKind } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { fromInput, toInput } from './schedule/time'

const COLORS: Record<ScheduleKind, string> = { talk: 'bit', tournament: 'warn', meal: 'up', quiet: 'cyan', other: 'gray' }

type Draft = { title: string; kind: ScheduleKind; start: string; end: string; where: string; note: string }
const blank: Draft = { title: '', kind: 'other', start: '', end: '', where: '', note: '' }

function ItemForm({ item, kinds, onDone }: { item: ScheduleItem | null; kinds: ScheduleKind[]; onDone: () => void }) {
  const { t } = useTranslation()
  const [d, setD] = useState<Draft>(() => item
    ? { title: item.title, kind: item.kind, start: toInput(item.start), end: item.end ? toInput(item.end) : '', where: item.where, note: item.note }
    : blank)
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) => { const v = e.currentTarget.value; setD((x) => ({ ...x, [k]: v })) }
  const save = useMutation({
    mutationFn: () => {
      const body = { ...d, start: fromInput(d.start), end: d.end ? fromInput(d.end) : null }
      return item ? patch(`/api/schedule/items/${item.id}`, body) : post('/api/schedule/items', body)
    },
    onSuccess: onDone,
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="sm">
        <Title order={2} size="h4">{item ? t('schedule.editItem') : t('schedule.addItem')}</Title>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t('schedule.itemTitle')} required maxLength={120} value={d.title} onChange={set('title')} />
          <Select label={t('schedule.kindLabel')} value={d.kind} allowDeselect={false}
            data={kinds.map((k) => ({ value: k, label: t(`schedule.kind.${k}`) }))} onChange={(v) => setD((x) => ({ ...x, kind: (v ?? 'other') as ScheduleKind }))} />
          <TextInput type="datetime-local" label={t('schedule.start')} required value={d.start} onChange={set('start')} />
          <TextInput type="datetime-local" label={t('schedule.end')} value={d.end} onChange={set('end')} />
          <TextInput label={t('schedule.where')} maxLength={120} value={d.where} onChange={set('where')} />
          <TextInput label={t('schedule.note')} maxLength={500} value={d.note} onChange={set('note')} />
        </SimpleGrid>
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group gap="xs">
          <Button loading={save.isPending} disabled={!d.title.trim() || !d.start} onClick={() => save.mutate()}>{t('schedule.save')}</Button>
          <Button variant="default" onClick={onDone}>{t('schedule.cancel')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

function EventTimes({ data, canEdit }: { data: ScheduleData; canEdit: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [start, setStart] = useState(data.event.start ? toInput(data.event.start) : '')
  const [end, setEnd] = useState(data.event.end ? toInput(data.event.end) : '')
  const save = useMutation({
    mutationFn: () => put('/api/schedule/event', { start: start ? fromInput(start) : null, end: end ? fromInput(end) : null }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.schedule }),
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Text fw={600} mb={4}>{t('schedule.event')}</Text>
      <Text size="sm" c="dimmed" mb="sm">{t('schedule.eventHelp')}</Text>
      <Group align="flex-end" gap="sm">
        <TextInput type="datetime-local" label={t('schedule.eventStart')} value={start} disabled={!canEdit} onChange={(e) => setStart(e.currentTarget.value)} />
        <TextInput type="datetime-local" label={t('schedule.eventEnd')} value={end} disabled={!canEdit} onChange={(e) => setEnd(e.currentTarget.value)} />
        {canEdit && <Button variant="default" loading={save.isPending} onClick={() => save.mutate()}>{t('schedule.saveEvent')}</Button>}
      </Group>
      {save.error && <Alert mt="sm" color="down" role="alert">{save.error.message}</Alert>}
      {save.isSuccess && <Text size="sm" c="up" mt="xs" role="status">{t('schedule.saved')}</Text>}
    </Paper>
  )
}

/** The event's programme (issue #106). Leads plan it here; attendees see it on /agenda. */
export default function Schedule() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const query = useQuery({ queryKey: qk.schedule, queryFn: () => get<ScheduleData>('/api/schedule') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.schedule })
  useLiveEvent('schedule.changed', refresh)
  const [editing, setEditing] = useState<'new' | string | null>(null)
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/schedule/items/${id}`), onSuccess: refresh })
  const upload = useMutation({
    mutationFn: async (file: File) => post<{ added: number; updated: number; removed: number }>('/api/schedule/import', {
      ics: await file.text(), tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
    onSuccess: refresh,
  })
  const d = query.data
  const day = (ts: number) => new Date(ts * 1000).toLocaleDateString(i18n.language, { weekday: 'long', day: 'numeric', month: 'long' })
  const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
  const days: [string, ScheduleItem[]][] = []
  for (const item of d?.items ?? []) {
    const key = day(item.start)
    if (days.length && days[days.length - 1][0] === key) days[days.length - 1][1].push(item)
    else days.push([key, [item]])
  }
  const err = remove.error || upload.error

  return (
    <Layout title={t('schedule.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('schedule.title')} desc={t('schedule.intro')}
        actions={canEdit ? (
          <Group gap="xs">
            <FileButton accept=".ics,text/calendar" onChange={(f) => f && upload.mutate(f)}>
              {(props) => <Button {...props} variant="default" loading={upload.isPending} leftSection={<IconUpload size={16} />}>{t('schedule.import')}</Button>}
            </FileButton>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>{t('schedule.addItem')}</Button>
          </Group>
        ) : undefined} />
      {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
      {err && <Alert color="down" role="alert" mb="sm">{err.message}</Alert>}
      {upload.data && (
        <Alert color="up" role="status" mb="sm" withCloseButton onClose={() => upload.reset()}>
          {t('schedule.imported', upload.data)}
        </Alert>
      )}
      {query.isPending || !d ? <Loader aria-label={t('common.loading')} /> : (
        <Stack gap="md">
          <Text size="sm">
            {d.public
              ? <>{t('schedule.publicOn')} <Anchor href="/agenda" target="_blank">/agenda</Anchor> · <Anchor href="/agenda?screen=1" target="_blank">{t('schedule.bigScreen')}</Anchor></>
              : t('schedule.publicOff')}
          </Text>
          <EventTimes key={`${d.event.start}-${d.event.end}`} data={d} canEdit={canEdit} />
          {editing && (
            <ItemForm key={editing} item={editing === 'new' ? null : d.items.find((i) => i.id === editing) ?? null} kinds={d.kinds}
              onDone={() => { setEditing(null); refresh() }} />
          )}
          {days.length === 0 ? (
            <Paper withBorder radius="lg" p="lg">
              <Group gap="sm" wrap="nowrap"><IconCalendarPlus size={22} /><Text c="dimmed">{t('schedule.empty')}</Text></Group>
            </Paper>
          ) : days.map(([label, items]) => (
            <Paper key={label} withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{label}</Title>
              <Table.ScrollContainer minWidth={560}>
                <Table verticalSpacing="xs">
                  <Table.Tbody>
                    {items.map((i) => (
                      <Table.Tr key={i.id}>
                        <Table.Td w={190} style={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{clock(i.start)}{i.end ? `–${clock(i.end)}` : ''}</Table.Td>
                        <Table.Td>
                          <Text fw={600}>{i.title}</Text>
                          {(i.where || i.note) && <Text size="xs" c="dimmed">{[i.where, i.note].filter(Boolean).join(' · ')}</Text>}
                        </Table.Td>
                        <Table.Td w={200}>
                          <Group gap={4} wrap="nowrap">
                            <Badge variant="light" color={COLORS[i.kind]} tt="none">{t(`schedule.kind.${i.kind}`)}</Badge>
                            {i.source === 'ical' && <Badge variant="outline" color="gray" tt="none">iCal</Badge>}
                          </Group>
                        </Table.Td>
                        {canEdit && (
                          <Table.Td w={80}>
                            <Group gap={4} wrap="nowrap">
                              <ActionIcon variant="subtle" aria-label={t('schedule.editNamed', { title: i.title })} onClick={() => setEditing(i.id)}><IconPencil size={16} /></ActionIcon>
                              <ActionIcon variant="subtle" color="down" aria-label={t('schedule.deleteNamed', { title: i.title })} onClick={() => remove.mutate(i.id)}><IconTrash size={16} /></ActionIcon>
                            </Group>
                          </Table.Td>
                        )}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
          ))}
          <Text size="xs" c="dimmed">{t('schedule.importHint')}</Text>
        </Stack>
      )}
    </Layout>
  )
}
