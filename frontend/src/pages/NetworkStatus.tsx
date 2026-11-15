import {
  ActionIcon, Alert, Badge, Button, Group, Loader, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { IconExternalLink, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { StatusArea, StatusPageData, StatusState } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const BY_HAND: StatusState[] = ['operational', 'degraded', 'outage', 'maintenance']
const COLOR: Record<StatusState, string> = {
  operational: 'up', degraded: 'warn', outage: 'down', maintenance: 'warn', unknown: 'gray',
}

function AreaLine({ a }: { a: StatusArea }) {
  const { t } = useTranslation()
  const where = a.block ? t('status.block', { name: a.block }) : a.hall ? t('status.hall', { name: a.hall }) : t('status.somewhere')
  const bits = [a.hall && a.block ? a.hall : '', a.rows ? t('status.rows', { rows: a.rows }) : '',
    a.seats ? t('status.seats', { count: a.seats }) : ''].filter(Boolean)
  return (
    <div>
      <Text size="sm" fw={600}>{where}</Text>
      <Text size="xs" c="dimmed">
        {[...bits, a.switches?.length ? t('status.switches', { names: a.switches.join(', ') }) : ''].filter(Boolean).join(' · ')}
      </Text>
    </div>
  )
}

/** What attendees see on /status, and what the crew posts there (issue #101). */
export default function NetworkStatus() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const canSet = useCan('incidents.assign')
  const query = useQuery({ queryKey: qk.statusPage, queryFn: () => get<StatusPageData>('/api/status-page'), refetchInterval: 30_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.statusPage })
  useLiveEvent('status_page.changed', refresh)
  useLiveEvent('switch.status', refresh)
  const [text, setText] = useState('')
  const [area, setArea] = useState('')
  const [pick, setPick] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const postUpdate = useMutation({
    mutationFn: () => post('/api/status-page/updates', { text, area }),
    onSuccess: () => { setText(''); setArea(''); refresh() },
  })
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/status-page/updates/${id}`), onSuccess: refresh })
  const override = useMutation({
    mutationFn: (state: string | null) => put('/api/status-page/override', { state, note }),
    onSuccess: () => { setPick(null); setNote(''); refresh() },
  })
  const d = query.data
  const when = (at: number) => new Date(at * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
  const error = postUpdate.error || remove.error || override.error

  return (
    <Layout title={t('status.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('status.title')} desc={t('status.intro')}
        actions={
          <Button variant="default" component="a" href="/status" target="_blank" leftSection={<IconExternalLink size={16} />}>
            {t('status.open')}
          </Button>
        } />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        {query.isPending || !d ? <Loader aria-label={t('common.loading')} /> : (
          <>
            {!d.public && <Alert color="gray" variant="light">{t('status.publicOff')}</Alert>}
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Paper withBorder radius="lg" p="md">
                <Text size="xs" c="dimmed">{t('status.shows')}</Text>
                <Group gap="sm" mt={4}>
                  <Badge size="lg" color={COLOR[d.state]} variant="filled" tt="none" data-testid="state">{t(`status.state.${d.state}`)}</Badge>
                  {d.since && <Text size="sm" c="dimmed">{t('status.since', { time: when(d.since) })}</Text>}
                </Group>
                <Text size="sm" mt="xs">
                  {d.override
                    ? t('status.setBy', { state: t(`status.state.${d.override.state}`), who: d.override.by ?? '–', time: when(d.override.at),
                      auto: t(`status.state.${d.auto_state}`) })
                    : t('status.automatic')}
                </Text>
                {d.override?.note && <Text size="sm" c="dimmed">{d.override.note}</Text>}
                {canSet && (
                  <Stack gap="xs" mt="md">
                    <Group gap="xs" align="flex-end" wrap="wrap">
                      <Select label={t('status.setState')} value={pick} onChange={setPick} w={200}
                        data={BY_HAND.map((s) => ({ value: s, label: t(`status.state.${s}`) }))} />
                      <TextInput label={t('status.note')} value={note} onChange={(e) => setNote(e.currentTarget.value)}
                        maxLength={200} style={{ flex: 1, minWidth: 160 }} />
                    </Group>
                    <Group gap="xs">
                      <Button disabled={!pick} loading={override.isPending && !!pick} onClick={() => override.mutate(pick)}>{t('status.set')}</Button>
                      {d.override && (
                        <Button variant="default" loading={override.isPending && !pick} onClick={() => override.mutate(null)}>
                          {t('status.backToAuto')}
                        </Button>
                      )}
                    </Group>
                  </Stack>
                )}
              </Paper>
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h5" mb="xs">{t('status.areas')}</Title>
                {d.crew_areas.length === 0 ? <Text size="sm" c="dimmed">{t('status.noAreas')}</Text> : (
                  <Stack gap="xs">{d.crew_areas.map((a) => <AreaLine key={`${a.hall}-${a.block}`} a={a} />)}</Stack>
                )}
                <Text size="xs" c="dimmed" mt="sm">{d.switch_names ? t('status.namesShown') : t('status.namesHidden')}</Text>
              </Paper>
            </SimpleGrid>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h5" mb="xs">{t('status.updates')}</Title>
              {canSet && (
                <Stack gap="xs" mb="md">
                  <Textarea label={t('status.newUpdate')} placeholder={t('status.placeholder')} autosize minRows={2} maxLength={500}
                    value={text} onChange={(e) => setText(e.currentTarget.value)} />
                  <Group gap="xs" align="flex-end">
                    <TextInput label={t('status.area')} placeholder={t('status.areaPlaceholder')} value={area} maxLength={80}
                      onChange={(e) => setArea(e.currentTarget.value)} style={{ flex: 1 }} />
                    <Button disabled={!text.trim()} loading={postUpdate.isPending} onClick={() => postUpdate.mutate()}>{t('status.post')}</Button>
                  </Group>
                </Stack>
              )}
              {d.updates.length === 0 ? <Text size="sm" c="dimmed">{t('status.noUpdates')}</Text> : (
                <Stack gap="xs">
                  {d.updates.map((u) => (
                    <Group key={u.id} gap="sm" wrap="nowrap" align="flex-start" justify="space-between">
                      <div style={{ minWidth: 0 }}>
                        <Text size="xs" c="dimmed">{[when(u.at), u.area].filter(Boolean).join(' · ')}</Text>
                        <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{u.text}</Text>
                      </div>
                      {canSet && (
                        <ActionIcon variant="subtle" color="down" aria-label={t('status.remove')} onClick={() => remove.mutate(u.id)}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      )}
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>
          </>
        )}
      </Stack>
    </Layout>
  )
}
