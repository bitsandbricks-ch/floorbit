import {
  Alert, Badge, Button, Chip, Group, Loader, Paper, SegmentedControl, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { IconDownload, IconSearch } from '@tabler/icons-react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { TimelineData, TimelineEntry, TimelineKind } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const KINDS: TimelineKind[] = ['change', 'outage', 'incident', 'alert', 'deploy', 'sign-in']
const RANGES = ['6', '24', '0'] as const
const KIND_COLOR: Record<TimelineKind, string> = {
  change: 'trace', 'sign-in': 'gray', outage: 'down', incident: 'warn', alert: 'warn', deploy: 'bit',
}
const SEVERITY_COLOR = { up: 'var(--color-up)', down: 'var(--color-down)', warn: 'var(--color-warn)', info: 'var(--color-muted)' }

function dayOf(t: number, lang: string) {
  return new Date(t * 1000).toLocaleDateString(lang, { weekday: 'long', day: 'numeric', month: 'long' })
}

function Row({ e, lang }: { e: TimelineEntry; lang: string }) {
  const { t } = useTranslation()
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start" py={6} className="fb-timeline-row" data-kind={e.kind}>
      <Text size="sm" c="dimmed" ff="monospace" style={{ whiteSpace: 'nowrap' }}>
        {new Date(e.t * 1000).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </Text>
      <span className="fb-timeline-dot" style={{ background: e.severity ? SEVERITY_COLOR[e.severity] : 'var(--color-line)' }} />
      <Badge variant="light" color={KIND_COLOR[e.kind]} tt="none" w={92} style={{ flexShrink: 0 }}>{t(`timeline.kind.${e.kind}`)}</Badge>
      <div style={{ minWidth: 0 }}>
        <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>{e.title}</Text>
        {(e.target || e.who) && (
          <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            {[e.target, e.who ? t('timeline.by', { who: e.who }) : ''].filter(Boolean).join(' · ')}
          </Text>
        )}
      </div>
    </Group>
  )
}

/** Every change during the LAN on one timeline: edits, outages, incidents, alerts and deploys (issue #100). */
export default function Timeline() {
  const { t, i18n } = useTranslation()
  const [kinds, setKinds] = useState<string[]>(KINDS.filter((k) => k !== 'sign-in'))
  const [search, setSearch] = useState('')
  const [hours, setHours] = useState<string>('24')
  const params = new URLSearchParams()
  if (kinds.length && kinds.length < KINDS.length) params.set('kinds', kinds.join(','))
  if (search.trim()) params.set('q', search.trim())
  if (hours !== '0') params.set('hours', hours)
  const query = params.toString()
  const list = useInfiniteQuery({
    queryKey: qk.timeline(query),
    queryFn: ({ pageParam }) => get<TimelineData>(`/api/timeline?${query}${pageParam ? `&before=${pageParam}` : ''}`),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.more && last.entries.length ? last.entries[last.entries.length - 1].t : undefined),
    refetchInterval: 60_000,
  })
  useLiveEvent('incident.changed', () => void list.refetch())
  const first = list.data?.pages[0]
  const rows = list.data?.pages.flatMap((p) => p.entries) ?? []
  const days: [string, TimelineEntry[]][] = []
  for (const e of rows) {
    const day = dayOf(e.t, i18n.language)
    if (days.length && days[days.length - 1][0] === day) days[days.length - 1][1].push(e)
    else days.push([day, [e]])
  }

  return (
    <Layout title={t('timeline.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('timeline.title')} desc={t('timeline.intro')}
        actions={
          <Group gap="xs">
            <Button variant="default" component="a" leftSection={<IconDownload size={16} />} href={`/api/timeline.csv?${query}`}>CSV</Button>
            <Button variant="default" component="a" leftSection={<IconDownload size={16} />} href={`/api/timeline?${query}&format=json`}>JSON</Button>
          </Group>
        } />
      <Stack gap="md">
        <Group gap="sm" wrap="wrap">
          <TextInput leftSection={<IconSearch size={14} />} aria-label={t('timeline.search')} placeholder={t('timeline.search')}
            value={search} onChange={(e) => setSearch(e.currentTarget.value)} style={{ flex: 1, minWidth: 220 }} />
          <SegmentedControl value={hours} onChange={setHours} aria-label={t('timeline.range')}
            data={RANGES.map((h) => ({ value: h, label: t(`timeline.hours.${h}`) }))} />
        </Group>
        <Chip.Group multiple value={kinds} onChange={setKinds}>
          <Group gap="xs">
            {KINDS.map((k) => (
              <Chip key={k} value={k} size="sm" color={KIND_COLOR[k]}>
                {t(`timeline.kind.${k}`)}{first ? ` (${first.counts[k] ?? 0})` : ''}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
        {list.error && <Alert color="down" role="alert">{t('common.error', { message: list.error.message })}</Alert>}
        {list.isPending ? <Loader aria-label={t('common.loading')} /> : rows.length === 0 ? (
          <Text c="dimmed">{t('timeline.empty')}</Text>
        ) : (
          <>
            {days.map(([day, entries]) => (
              <Paper key={day} withBorder radius="lg" p="md">
                <Title order={2} size="h5" mb={4}>{day}</Title>
                {entries.map((e, n) => <Row key={`${e.t}-${n}`} e={e} lang={i18n.language} />)}
              </Paper>
            ))}
            <Group justify="space-between">
              <Text size="sm" c="dimmed">{t('timeline.showing', { shown: rows.length, total: first?.total ?? rows.length })}</Text>
              {list.hasNextPage && (
                <Button variant="default" loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
                  {t('timeline.older')}
                </Button>
              )}
            </Group>
          </>
        )}
      </Stack>
    </Layout>
  )
}
