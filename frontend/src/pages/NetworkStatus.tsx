import {
  Alert, Autocomplete, Badge, Button, Group, Select, SimpleGrid, Stack, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { IconExternalLink, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { StatusArea, StatusPageData, StatusState, StatusUpdate } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { DataTable, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { clock } from '@/lib/time'
import { COLOR } from './status/state'
import { ConfirmIcon } from '@bitsandbricks/ui'

const BY_HAND: StatusState[] = ['operational', 'degraded', 'outage', 'maintenance']
const AUTO = 'auto'

type T = ReturnType<typeof useTranslation>['t']

function whereOf(a: StatusArea, t: T) {
  return a.block ? t('status.block', { name: a.block }) : a.hall ? t('status.hall', { name: a.hall }) : t('status.somewhere')
}

export function AreaLine({ a }: { a: StatusArea }) {
  const { t } = useTranslation()
  const where = whereOf(a, t)
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
  // Known places to pick from; still free text, so "LAN cache" or "Catering" can be typed too (#1416).
  const places = (kind: 'halls' | 'blocks') => ({
    queryKey: qk.options(kind, ''), staleTime: 60_000,
    queryFn: () => get<{ options: { label: string }[] }>(`/api/options/${kind}`),
  })
  const hallNames = useQuery(places('halls')).data?.options.map((o) => o.label) ?? []
  // Named as attendees read them elsewhere on the page: "Seat block A".
  const blockNames = useQuery(places('blocks')).data?.options.map((o) => t('status.block', { name: o.label })) ?? []
  const areaData = [
    { group: t('statusArea.halls'), items: [...new Set(hallNames)] },
    { group: t('statusArea.blocks'), items: [...new Set(blockNames)].filter((b) => !hallNames.includes(b)) },
  ].filter((g) => g.items.length)
  // The picker shows what decides the state now: "Automatic" or the state set by hand (#890, #1416).
  // Choosing Automatic is how a state set by hand is lifted.
  const current = d?.override?.state ?? AUTO
  const chosen = pick ?? current
  // One-click starting points from what the public page shows (never switch names): edit, then post.
  const suggestions = d ? [
    ...d.areas.map((a) => ({ a, kind: 'Down', color: 'down' })),
    ...d.recovered.map((a) => ({ a, kind: 'Back', color: 'up' })),
  ].map(({ a, kind, color }) => {
    const where = whereOf(a, t)
    return { key: `${kind}-${a.hall}-${a.block}`, where, color, label: t(`status.suggest${kind}`, { where }),
      text: t(`status.suggest${kind}Text`, { where }) }
  }) : []
  const when = (at: number) => clock(at, i18n.language)
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
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        {query.isPending || !d ? <LoadingState rows={3} /> : (
          <>
            {!d.public && <Alert color="gray" variant="light">{t('status.publicOff')}</Alert>}
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Panel>
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
                {(d.reasons ?? []).length > 0 && (
                  <Text size="sm" c="dimmed" mt={4}>
                    {(d.reasons ?? []).map((r) => t(`publicStatus.reason.${r}`, { defaultValue: r })).join(' ')}
                  </Text>
                )}
                {d.override?.note && <Text size="sm" c="dimmed">{d.override.note}</Text>}
                {canSet && (
                  <Stack gap="xs" mt="md">
                    <Group gap="xs" align="flex-end" wrap="wrap">
                      <Select label={t('status.setState')} value={chosen} onChange={setPick} w={300} allowDeselect={false}
                        data={[
                          { value: AUTO, label: t('statusArea.automatic', { state: t(`status.state.${d.auto_state}`) }) },
                          ...BY_HAND.map((s) => ({ value: s, label: t(`status.state.${s}`) })),
                        ]} />
                      <TextInput label={t('status.note')} value={note} onChange={(e) => setNote(e.currentTarget.value)}
                        maxLength={200} style={{ flex: 1, minWidth: 160 }} />
                    </Group>
                    <Group gap="xs">
                      <Button disabled={chosen === current && !note.trim()} loading={override.isPending}
                        onClick={() => override.mutate(chosen === AUTO ? null : chosen)}>{t('status.set')}</Button>
                    </Group>
                  </Stack>
                )}
              </Panel>
              <Panel title={t('status.areas')}>
                {d.crew_areas.length === 0 ? <Text size="sm" c="dimmed">{t('status.noAreas')}</Text> : (
                  <Stack gap="xs">{d.crew_areas.map((a) => <AreaLine key={`${a.hall}-${a.block}`} a={a} />)}</Stack>
                )}
                {d.crew_recovered.length > 0 && (
                  <Stack gap="xs" mt="md" data-testid="recovered">
                    <div>
                      <Title order={3} size="h6">{t('status.recovered')}</Title>
                      {d.recovered_at && <Text size="xs" c="dimmed">{t('status.recoveredAt', { time: when(d.recovered_at) })}</Text>}
                    </div>
                    {d.crew_recovered.map((a) => <AreaLine key={`back-${a.hall}-${a.block}`} a={a} />)}
                  </Stack>
                )}
                <Text size="xs" c="dimmed" mt="sm">{t('status.namesHidden')}</Text>
              </Panel>
            </SimpleGrid>
            <Panel title={t('status.updates')}>
              {canSet && (
                <Stack gap="xs" mb="md">
                  {suggestions.length > 0 && (
                    <Group gap={6} data-testid="suggestions">
                      <Text size="xs" c="dimmed">{t('status.suggestions')}</Text>
                      {suggestions.map((s) => (
                        <Button key={s.key} size="compact-xs" variant="light" color={s.color}
                          onClick={() => { setText(s.text); setArea(s.where) }}>{s.label}</Button>
                      ))}
                    </Group>
                  )}
                  <Textarea label={t('status.newUpdate')} placeholder={t('status.placeholder')} autosize minRows={2} maxLength={500}
                    value={text} onChange={(e) => setText(e.currentTarget.value)} />
                  <Group gap="xs" align="flex-end">
                    <Autocomplete label={t('status.area')} placeholder={t('status.areaPlaceholder')} value={area} maxLength={80}
                      onChange={setArea} data={areaData} style={{ flex: 1 }} />
                    <Button disabled={!text.trim()} loading={postUpdate.isPending} onClick={() => postUpdate.mutate()}>{t('status.post')}</Button>
                  </Group>
                </Stack>
              )}
              {/* The shared table, like every list in the app (issue #890): newest first, ten to a page. */}
              <DataTable label={t('status.updates')} rows={d.updates} rowKey={(u) => u.id} pageSize={10} pager="compact" bare cards
                defaultSort={{ id: 'when', desc: true }}
                empty={<Text size="sm" c="dimmed">{t('status.noUpdates')}</Text>}
                columns={[
                  { id: 'when', header: t('statusUpdates.when'), sort: (u) => u.at, descFirst: true, card: 'inline', cell: (u) => when(u.at) },
                  { id: 'area', header: t('statusUpdates.area'), sort: (u) => u.area ?? '', card: 'inline',
                    cell: (u) => u.area || <Text span size="sm" c="dimmed">{t('statusUpdates.everywhere')}</Text> },
                  { id: 'text', header: t('statusUpdates.text'), wrap: true, cell: (u) => u.text },
                  ...(canSet ? [{ id: 'remove', header: '', width: 44, card: 'actions' as const, cell: (u: StatusUpdate) => (
                    <ConfirmIcon label={t('status.remove')} onConfirm={() => remove.mutate(u.id)}>
                      <IconTrash size={16} />
                    </ConfirmIcon>
                  ) }] : []),
                ]} />
            </Panel>
          </>
        )}
      </Stack>
    </Layout>
  )
}
