import { Anchor, Badge, Group, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EndpointAnswer, EndpointRow } from '@/api/types'
import { DataTable } from '@/components/DataTable'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { ago, dateTime } from '@/lib/time'

// Seen in the last two minutes: the collector looks every minute.
const NOW_WINDOW = 120

/** Where each machine was seen (docs/endpoints.md): search an IP or MAC, or open a port's or a
 *  seat's history. ?q=, ?seat= or ?device=&port= so the floor plan and Go to can link here. */
export default function Endpoints() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const seat = params.get('seat') ?? ''
  const device = params.get('device') ?? ''
  const port = params.get('port') ?? ''
  const [text, setText] = useState(q)
  // Follow the address when it changes from outside (a link, Back), not while typing.
  const [shownQ, setShownQ] = useState(q)
  if (q !== shownQ) {
    setShownQ(q)
    setText(q)
  }
  // Ask once typing pauses, and keep it in the address so the page can be shared and reloaded.
  useEffect(() => {
    if (text === q) return undefined
    const timer = setTimeout(() => setParams(text.trim() ? { q: text.trim() } : {}, { replace: true }), 250)
    return () => clearTimeout(timer)
  }, [text, q, setParams])

  const ask = seat ? `seat=${encodeURIComponent(seat)}`
    : device && port ? `device=${encodeURIComponent(device)}&port=${encodeURIComponent(port)}`
      : q.length >= 2 ? `q=${encodeURIComponent(q)}` : ''
  const query = useQuery({
    queryKey: qk.endpoints(ask),
    // Nothing asked: the newest sightings anywhere, so the page opens with something (issue #872).
    queryFn: () => get<EndpointAnswer>(ask ? `/api/endpoints?${ask}` : '/api/endpoints'),
    refetchInterval: 60_000,
  })
  const rows = query.data?.rows ?? []
  // "Now" is when the answer came, so a row doesn't stay "now" on a page left open.
  const now = query.dataUpdatedAt / 1000
  const scope = seat ? t('endpoints.scope.seat', { seat }) : device && port ? t('endpoints.scope.port', { device, port }) : null

  const portLink = (r: EndpointRow) => (r.port
    ? <Anchor component={Link} to={`/endpoints?device=${encodeURIComponent(r.device)}&port=${encodeURIComponent(r.port)}`}>{r.device} {r.port}</Anchor>
    : <Text span c="dimmed">{t('endpoints.arpOnly', { device: r.device })}</Text>)

  return (
    <Layout title={t('endpoints.title')}>
      <PageHead title={t('endpoints.title')} desc={t('endpoints.intro')} />
      <Stack gap="md">
        <TextInput
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          placeholder={t('endpoints.placeholder')}
          aria-label={t('endpoints.placeholder')}
          leftSection={<IconSearch size={16} aria-hidden="true" />}
          maw={480}
        />
        {scope && (
          <Group gap="xs">
            <Text fw={600}>{scope}</Text>
            <Anchor component={Link} to="/endpoints">{t('endpoints.clear')}</Anchor>
          </Group>
        )}
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {query.data?.status.error && <ErrorBanner error={query.data.status.error} />}
        {!ask && <Text size="sm" c="dimmed">{t('endpoints.latest')}</Text>}
        {query.isPending ? <LoadingState rows={3} /> : !rows.length ? (
          (ask ? <EmptyState title={t('endpoints.none')} description={t('endpoints.noneDesc', { days: query.data?.status.keep_days ?? 7 })} />
          : <EmptyState title={t('endpoints.nothingYet')} description={t('endpoints.startDesc')} />)
        ) : (
          <Panel padding={0}>
            <DataTable label={t('endpoints.title')} rows={rows} rowKey={(r) => `${r.mac}|${r.ip}|${r.device}|${r.port}|${r.first_seen}`}
              defaultSort={{ id: 'seen', desc: true }} minWidth={760} bare striped
              columns={[
                { id: 'ip', header: t('endpoints.col.ip'), sort: (r) => r.ip ?? '', mono: true, cell: (r) => r.ip ?? '–' },
                { id: 'mac', header: t('endpoints.col.mac'), sort: (r) => r.mac, mono: true, cell: (r) => r.mac },
                { id: 'port', header: t('endpoints.col.port'), sort: (r) => `${r.device} ${r.port}`, cell: (r) => portLink(r) },
                { id: 'seat', header: t('endpoints.col.seat'), sort: (r) => r.seat ?? '', cell: (r) =>
                  (r.seat ? <Anchor component={Link} to={`/endpoints?seat=${encodeURIComponent(r.seat)}`}>{r.seat}</Anchor> : '–') },
                { id: 'vlan', header: t('endpoints.col.vlan'), sort: (r) => r.vlan ?? -1, hideOnPhone: true, cell: (r) => r.vlan ?? '–' },
                { id: 'seen', header: t('endpoints.col.seen'), sort: (r) => r.last_seen, cell: (r) => (
                  <Group gap={6} wrap="nowrap">
                    {now - r.last_seen < NOW_WINDOW
                      ? <Badge color="up" variant="light" tt="none">{t('endpoints.now')}</Badge>
                      : <Text span size="sm">{ago(r.last_seen)}</Text>}
                    <Text span size="xs" c="dimmed">{t('endpoints.since', { when: dateTime(r.first_seen) })}</Text>
                  </Group>
                ) },
              ]} />
          </Panel>
        )}
      </Stack>
    </Layout>
  )
}
