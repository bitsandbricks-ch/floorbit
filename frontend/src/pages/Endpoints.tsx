import { Anchor, Badge, Group, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EndpointAnswer, EndpointRow } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { EmptyState, ErrorBanner, LoadingState, Panel } from '@/components/ui'
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
    queryFn: () => get<EndpointAnswer>(`/api/endpoints?${ask}`),
    enabled: Boolean(ask),
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
        {!ask ? (
          <EmptyState title={t('endpoints.start')} desc={t('endpoints.startDesc')} />
        ) : query.isPending ? <LoadingState /> : !rows.length ? (
          <EmptyState title={t('endpoints.none')} desc={t('endpoints.noneDesc', { days: query.data?.status.keep_days ?? 7 })} />
        ) : (
          <Panel padding={0}>
            <Table.ScrollContainer minWidth={760}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('endpoints.col.ip')}</Table.Th>
                    <Table.Th>{t('endpoints.col.mac')}</Table.Th>
                    <Table.Th>{t('endpoints.col.port')}</Table.Th>
                    <Table.Th>{t('endpoints.col.seat')}</Table.Th>
                    <Table.Th>{t('endpoints.col.vlan')}</Table.Th>
                    <Table.Th>{t('endpoints.col.seen')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((r) => (
                    <Table.Tr key={`${r.mac}|${r.ip}|${r.device}|${r.port}|${r.first_seen}`}>
                      <Table.Td ff="monospace">{r.ip ?? '–'}</Table.Td>
                      <Table.Td ff="monospace">{r.mac}</Table.Td>
                      <Table.Td>{portLink(r)}</Table.Td>
                      <Table.Td>
                        {r.seat ? <Anchor component={Link} to={`/endpoints?seat=${encodeURIComponent(r.seat)}`}>{r.seat}</Anchor> : '–'}
                      </Table.Td>
                      <Table.Td>{r.vlan ?? '–'}</Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          {now - r.last_seen < NOW_WINDOW
                            ? <Badge color="up" variant="light" tt="none">{t('endpoints.now')}</Badge>
                            : <Text span size="sm">{ago(r.last_seen)}</Text>}
                          <Text span size="xs" c="dimmed">{t('endpoints.since', { when: dateTime(r.first_seen) })}</Text>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Panel>
        )}
      </Stack>
    </Layout>
  )
}
