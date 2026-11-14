import { Alert, Anchor, Badge, Button, Group, Loader, Select, Switch, Table, Text, TextInput } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { SyslogLine, LogSeverity, LogStatus, LogsData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/syslog.md'
const SEVERITIES: LogSeverity[] = ['emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug']
const COLOR: Record<LogSeverity, string> = {
  emerg: 'down', alert: 'down', crit: 'down', err: 'down', warning: 'warn', notice: 'blue', info: 'gray', debug: 'gray',
}
const PAGE = 200
const TAIL_MS = 3000

type Filters = { q: string; device: string; seat: string; port: string; severity: string }
const EMPTY: Filters = { q: '', device: '', seat: '', port: '', severity: '' }

function params(f: Filters, extra: Record<string, string | number> = {}) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries({ ...f, ...extra })) if (v !== '' && v != null) p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** Typing in the search box shouldn't ask the server on every key. */
function useSettled<T>(value: T, ms = 300) {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return settled
}

function StatusLine({ status }: { status: LogStatus }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  const dropped = status.counts.not_allowed + status.counts.rate_limited
  return (
    <Group gap="xs" mb="sm" wrap="wrap">
      {status.listening ? (
        <Badge color="up" variant="light" tt="none">
          {t(status.listening.tcp ? 'logs.listeningTcp' : 'logs.listening', { port: status.listening.port })}
        </Badge>
      ) : status.demo ? (
        <Badge color="gray" variant="light" tt="none">{t('logs.demo')}</Badge>
      ) : null}
      <Text size="xs" c="dimmed">
        {t('logs.kept', { count: status.lines, n: num(status.lines), hours: status.retention_hours })}
        {dropped > 0 && ` · ${t('logs.dropped', { allow: num(status.counts.not_allowed), rate: num(status.counts.rate_limited) })}`}
      </Text>
    </Group>
  )
}

function Row({ line, onDevice }: { line: SyslogLine; onDevice: (d: string) => void }) {
  const { t, i18n } = useTranslation()
  const time = new Date(line.ts * 1000).toLocaleString(i18n.language, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return (
    <Table.Tr>
      <Table.Td style={{ whiteSpace: 'nowrap' }}><Text size="xs" ff="monospace">{time}</Text></Table.Td>
      <Table.Td style={{ whiteSpace: 'nowrap' }}><Badge size="sm" variant="light" color={COLOR[line.severity]} tt="none">{t(`logs.sev.${line.severity}`)}</Badge></Table.Td>
      <Table.Td style={{ whiteSpace: 'nowrap' }}>
        <Anchor component="button" type="button" size="sm" onClick={() => onDevice(line.device)}
          title={t('logs.onlyDevice', { device: line.device })}>{line.device}</Anchor>
        {(line.port || line.seat) && (
          <Text size="xs" c="dimmed">
            {line.port}
            {line.seat && <> · <Anchor href={`/?seat=${encodeURIComponent(line.seat)}`} size="xs">{t('logs.seat', { seat: line.seat })}</Anchor></>}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>
          {line.program && <Text span c="dimmed" inherit>{line.program}: </Text>}
          {line.message}
        </Text>
      </Table.Td>
    </Table.Tr>
  )
}

/** Phones: one card-like block per line, the message on its own row at full width. */
function Compact({ line, onDevice }: { line: SyslogLine; onDevice: (d: string) => void }) {
  const { t, i18n } = useTranslation()
  const time = new Date(line.ts * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return (
    <li className="fb-log-line">
      <Group gap={6} wrap="wrap">
        <Badge size="sm" variant="light" color={COLOR[line.severity]} tt="none">{t(`logs.sev.${line.severity}`)}</Badge>
        <Text size="xs" ff="monospace" c="dimmed">{time}</Text>
        <Anchor component="button" type="button" size="sm" onClick={() => onDevice(line.device)}>{line.device}</Anchor>
        {line.port && <Text size="xs" c="dimmed">{line.port}</Text>}
        {line.seat && <Anchor href={`/?seat=${encodeURIComponent(line.seat)}`} size="xs">{t('logs.seat', { seat: line.seat })}</Anchor>}
      </Group>
      <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }} mt={2}>
        {line.program && <Text span c="dimmed" inherit>{line.program}: </Text>}
        {line.message}
      </Text>
    </li>
  )
}

/** Syslog from the event's switches, firewalls and DHCP servers (issue #91): search, filter and
 *  follow along. Lines name MACs and IPs, so the page needs seats.view like the API. */
export default function Logs() {
  const { t } = useTranslation()
  // Links from Problems and elsewhere open the page filtered: /logs?seat=A-4.
  const [search] = useSearchParams()
  const [filters, setFilters] = useState<Filters>(() => ({
    q: search.get('q') ?? '', device: search.get('device') ?? '', seat: search.get('seat') ?? '',
    port: search.get('port') ?? '', severity: SEVERITIES.includes(search.get('severity') as LogSeverity) ? search.get('severity')! : '',
  }))
  const [live, setLive] = useState(true)
  // Older pages belong to the filters they were read with; new filters start from the newest again.
  const [older, setOlder] = useState<{ key: string; lines: SyslogLine[]; more: boolean }>({ key: '', lines: [], more: true })
  const settled = useSettled(filters)
  const key = params(settled)
  const query = useQuery({
    queryKey: qk.logs(key),
    queryFn: () => get<LogsData>(`/api/logs${key}`),
    refetchInterval: live ? TAIL_MS : false,
    placeholderData: keepPreviousData,
  })
  const set = (k: keyof Filters) => (v: string | null) => setFilters((f) => ({ ...f, [k]: v ?? '' }))
  const data = query.data
  const olderLines = older.key === key ? older.lines : []
  const more = older.key === key ? older.more : true
  const lines = data ? [...data.lines, ...olderLines.filter((o) => o.id < (data.lines.at(-1)?.id ?? Infinity))] : []
  const [loadingOlder, setLoadingOlder] = useState(false)
  const loadOlder = async () => {
    const oldest = lines.at(-1)
    if (!oldest) return
    setLoadingOlder(true)
    try {
      const page = await get<LogsData>(`/api/logs${params(settled, { before: oldest.id })}`)
      setOlder((o) => ({ key, lines: [...(o.key === key ? o.lines : []), ...page.lines], more: page.lines.length >= PAGE }))
    } finally {
      setLoadingOlder(false)
    }
  }
  const filtered = Object.values(filters).some((v) => v !== '')
  const phone = useMediaQuery('(max-width: 48em)')

  return (
    <Layout title={t('logs.title')} back={{ href: '/', label: t('logs.floorplan') }}>
      <PageHead title={t('logs.title')} desc={t('logs.intro')}
        actions={<Switch label={t('logs.live')} checked={live} onChange={(e) => setLive(e.currentTarget.checked)} />} />
      {query.error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: query.error.message })}</Alert>}
      {data?.status.error && <Alert color="warn" mb="md">{data.status.error}</Alert>}
      <Group gap="sm" mb="sm" align="flex-end" wrap="wrap">
        <TextInput label={t('logs.search')} placeholder={t('logs.searchHint')} value={filters.q} style={{ flex: '2 1 220px' }}
          onChange={(e) => set('q')(e.currentTarget.value)} />
        <Select label={t('logs.device')} placeholder={t('logs.all')} data={data?.status.devices ?? []} value={filters.device || null}
          onChange={set('device')} clearable searchable style={{ flex: '1 1 160px' }} />
        <TextInput label={t('logs.seatFilter')} placeholder="A-12" value={filters.seat} style={{ flex: '0 1 110px' }}
          onChange={(e) => set('seat')(e.currentTarget.value)} />
        <TextInput label={t('logs.port')} placeholder="Gi1/0/4" value={filters.port} style={{ flex: '0 1 120px' }}
          onChange={(e) => set('port')(e.currentTarget.value)} />
        <Select label={t('logs.severity')} placeholder={t('logs.all')} value={filters.severity || null} onChange={set('severity')} clearable
          data={SEVERITIES.slice(0, -1).map((s) => ({ value: s, label: t('logs.atLeast', { level: t(`logs.sev.${s}`) }) }))}
          style={{ flex: '1 1 160px' }} />
        {filtered && <Button variant="default" onClick={() => setFilters(EMPTY)}>{t('logs.clear')}</Button>}
      </Group>
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : (
        <>
          <StatusLine status={data.status} />
          {!data.status.enabled && !data.status.demo && data.status.lines === 0 ? (
            <Alert color="gray" variant="light">{t('logs.off')} <Anchor href={DOCS}>docs/syslog.md</Anchor></Alert>
          ) : lines.length === 0 ? (
            <Text size="sm" c="dimmed">{filtered ? t('logs.noMatch') : t('logs.none')}</Text>
          ) : (
            <>
              {phone ? (
                <ul className="fb-log-lines" aria-label={t('logs.title')}>
                  {lines.map((l) => <Compact key={l.id} line={l} onDevice={set('device')} />)}
                </ul>
              ) : (
                <Table.ScrollContainer minWidth={640}>
                  <Table verticalSpacing={4} striped highlightOnHover aria-label={t('logs.title')}>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('logs.time')}</Table.Th>
                        <Table.Th>{t('logs.level')}</Table.Th>
                        <Table.Th>{t('logs.device')}</Table.Th>
                        <Table.Th>{t('logs.message')}</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {lines.map((l) => <Row key={l.id} line={l} onDevice={set('device')} />)}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
              {more && lines.length >= PAGE && (
                <Group justify="center" mt="sm">
                  <Button variant="default" loading={loadingOlder} onClick={() => void loadOlder()}>{t('logs.older')}</Button>
                </Group>
              )}
            </>
          )}
        </>
      )}
    </Layout>
  )
}
