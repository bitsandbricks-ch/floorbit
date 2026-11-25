import { Alert, Anchor, Badge, Button, Group, Loader, Pagination, SegmentedControl, Select, Switch, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMediaQuery } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EntitySelect } from '@/components/EntitySelect'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { LogSeverity, LogSource, LogStatus, LogsData, SyslogLine } from '@/api/types'
import { DataTable, ErrorBanner, PageHead } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { Message } from './logs/Message'
import { onPlan } from './plan/links'
import { clockSeconds, formatWhen } from '@/lib/time'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/syslog.md'
const SEVERITIES: LogSeverity[] = ['emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug']
const COLOR: Record<LogSeverity, string> = {
  emerg: 'down', alert: 'down', crit: 'down', err: 'down', warning: 'warn', notice: 'blue', info: 'gray', debug: 'gray',
}
const PAGE = 200          // lines per request to the server
const PAGE_SIZE = 50      // lines per page on screen (issue #1206)
const TAIL_MS = 3000
const STORE_MS = 15_000   // asking Loki every 3 seconds would be rude

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
      {(status.relayed ?? []).map((r) => (
        <Badge key={r.agent} color={r.recent ? 'up' : 'gray'} variant="light" tt="none">
          {t('logs.relayed', { agent: r.agent })}{r.dropped > 0 && ` · ${t('logs.relayDropped', { n: num(r.dropped) })}`}
        </Badge>
      ))}
      <Text size="xs" c="dimmed">
        {t('logs.kept', { count: status.lines, n: num(status.lines), hours: status.retention_hours })}
        {dropped > 0 && ` · ${t('logs.dropped', { allow: num(status.counts.not_allowed), rate: num(status.counts.rate_limited) })}`}
      </Text>
      {(status.stores ?? []).map((st) => st.error
        ? <Badge key={st.id} color="warn" variant="light" tt="none">{t('logs.storeError', { name: st.name, error: st.error })}</Badge>
        : <Text key={st.id} size="xs" c="dimmed">· {t('logs.storeSent', { name: st.name, n: num(st.sent ?? 0) })}</Text>)}
      {!!status.leases?.granted && (
        <Text size="xs" c="dimmed">· {t('logs.leases', { count: status.leases.granted, n: num(status.leases.granted) })}</Text>
      )}
    </Group>
  )
}

/** The log as the shared table: newest first as the server sends it, in pages; time, level and
 *  device sort the lines loaded so far (issue #1206). */
export function LogTable({ lines, store, source, onDevice }: { lines: SyslogLine[]; store: boolean; source: string; onDevice?: (d: string) => void }) {
  const { t, i18n } = useTranslation()
  return (
    <DataTable label={t('logs.title')} rows={lines} rowKey={(l, i) => (store ? `${l.id}-${i}` : String(l.id))} pageSize={PAGE_SIZE}
      striped density="compact" minWidth={640} defaultSort={{ id: 'time', desc: true }}
      count={(n) => t('logs.loaded', { count: n, n: n.toLocaleString(i18n.language) })}
      columns={[
        { id: 'time', header: t('logs.time'), mono: true, sort: (line) => line.ts, cell: (line) =>
          formatWhen(line.ts, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }, i18n.language) },
        { id: 'level', header: t('logs.level'), sort: (line) => SEVERITIES.indexOf(line.severity), cell: (line) =>
          <Badge size="sm" variant="light" color={COLOR[line.severity]} tt="none" miw="max-content">{t(`logs.sev.${line.severity}`)}</Badge> },
        { id: 'device', header: t(source === 'audit' ? 'logs.who' : 'logs.device'), sort: (line) => line.device, cell: (line) => (
          <>
            {onDevice ? (
              <Anchor component="button" type="button" size="sm" onClick={() => onDevice(line.device)}
                title={t('logs.onlyDevice', { device: line.device })}>{line.device}</Anchor>
            ) : <Text size="sm">{line.device}</Text>}
            {(line.port || line.seat) && (
              <Text size="xs" c="dimmed">
                {line.port}
                {line.seat && <> · <Anchor href={onPlan({ seat: line.seat })} size="xs" underline="always">{t('logs.seat', { seat: line.seat })}</Anchor></>}
              </Text>
            )}
          </>
        ) },
        { id: 'message', header: t('logs.message'), wrap: true, cell: (line) => (
          <Text size="sm" ff="monospace" component="div">
            <Message line={line} />
          </Text>
        ) },
      ]} />
  )
}

/** Phones: one card-like block per line, the message on its own row at full width. */
function Compact({ line, onDevice }: { line: SyslogLine; onDevice?: (d: string) => void }) {
  const { t, i18n } = useTranslation()
  const time = clockSeconds(line.ts, i18n.language)
  return (
    <li className="fb-log-line">
      <Group gap={6} wrap="wrap">
        <Badge size="sm" variant="light" color={COLOR[line.severity]} tt="none" miw="max-content">{t(`logs.sev.${line.severity}`)}</Badge>
        <Text size="xs" ff="monospace" c="dimmed">{time}</Text>
        {onDevice
          ? <Anchor component="button" type="button" size="sm" onClick={() => onDevice(line.device)}>{line.device}</Anchor>
          : <Text size="sm">{line.device}</Text>}
        {line.port && <Text size="xs" c="dimmed">{line.port}</Text>}
        {line.seat && <Anchor href={onPlan({ seat: line.seat })} size="xs" underline="always">{t('logs.seat', { seat: line.seat })}</Anchor>}
      </Group>
      <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }} mt={2} component="div">
        <Message line={line} />
      </Text>
    </li>
  )
}

// Each logs plugin's own query language, with an example for the box.
const QUERY: Record<string, { language: string; example: string }> = {
  loki: { language: 'LogQL', example: '{job="floorbit"} |= "err-disable"' },
  victorialogs: { language: 'LogsQL', example: 'device:sw-a-01 err-disable' },
}

/** Syslog from the event's switches, firewalls and DHCP servers (issue #91): search, filter and
 *  follow along. Lines name MACs and IPs, so the page needs seats.view like the API. With
 *  audit.read, the same viewer also shows Floorbit's own log and the audit log (issue #93). */
export default function Logs() {
  const { t } = useTranslation()
  // Links from Problems and elsewhere open the page filtered: /logs?seat=A-4.
  const [search, setSearch] = useSearchParams()
  const [filters, setFilters] = useState<Filters>(() => ({
    q: search.get('q') ?? '', device: search.get('device') ?? '', seat: search.get('seat') ?? '',
    port: search.get('port') ?? '', severity: SEVERITIES.includes(search.get('severity') as LogSeverity) ? search.get('severity')! : '',
  }))
  const [source, setSource] = useState<LogSource>(() => {
    const s = search.get('source')
    return s === 'app' || s === 'audit' || s?.startsWith('plugin:') ? (s as LogSource) : 'syslog'
  })
  const syslog = source === 'syslog'
  const store = source.startsWith('plugin:')
  // A logs plugin's query runs when it's sent (Enter), not on every key: half a query is an error.
  const [logql, setLogql] = useState('')
  const [draft, setDraft] = useState('')
  const [hours, setHours] = useState('24')
  const [live, setLive] = useState(true)
  // Older pages belong to the filters they were read with; new filters start from the newest again.
  const [older, setOlder] = useState<{ key: string; lines: SyslogLine[]; more: boolean }>({ key: '', lines: [], more: true })
  const settled = useSettled(filters)
  // The filters and the log live in the address too, so a reload or a pasted link shows the same
  // lines (issue #1206). A new filter starts again at the first page.
  useEffect(() => {
    setSearch((prev) => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(settled)) if (v) next.set(k, v); else next.delete(k)
      if (source === 'syslog') next.delete('source'); else next.set('source', source)
      if (next.toString() !== prev.toString()) next.delete('page')
      return next.toString() === prev.toString() ? prev : next
    }, { replace: true })
  }, [settled, source, setSearch])
  // Past the first page or sorted another way, new lines would move what you are reading: hold the tail.
  const browsing = (Number(search.get('page')) || 1) > 1 || !!search.get('sort')
  const following = live && !browsing
  // Seat, port and device only mean something in the syslog.
  const key = store
    ? params({ ...EMPTY, q: logql }, { source, hours })
    : params(syslog ? settled : { ...EMPTY, q: settled.q, severity: settled.severity }, syslog ? {} : { source })
  const query = useQuery({
    queryKey: qk.logs(key),
    queryFn: () => get<LogsData>(`/api/logs${key}`),
    refetchInterval: following ? (store ? STORE_MS : TAIL_MS) : false,
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
      const page = await get<LogsData>(`/api/logs${key}${key ? '&' : '?'}before=${oldest.id}`)
      setOlder((o) => ({ key, lines: [...(o.key === key ? o.lines : []), ...page.lines], more: page.lines.length >= PAGE }))
      // Straight to the first of the lines just read (the button only shows on the last page), instead of leaving them pages away.
      if (page.lines.length) {
        const first = Math.floor(lines.length / PAGE_SIZE) + 1
        setSearch((prev) => { const next = new URLSearchParams(prev); next.set('page', String(first)); return next }, { replace: true })
      }
    } finally {
      setLoadingOlder(false)
    }
  }
  const filtered = store ? logql !== '' : syslog ? Object.values(filters).some((v) => v !== '') : filters.q !== '' || filters.severity !== ''
  const sources = data?.status.sources ?? ['syslog']
  const onDevice = syslog ? set('device') : undefined
  // A logs plugin's line id is its time in microseconds: lines sent in one go share it, so it can't be the key alone.
  const storeName = (s: string) => data?.status.stores?.find((x) => `plugin:${x.id}` === s)?.name ?? s.slice('plugin:'.length)
  const phone = useMediaQuery('(max-width: 48em)')
  const pageCount = Math.max(1, Math.ceil(lines.length / PAGE_SIZE))
  const shownPage = Math.min(pageCount, Math.max(1, Number(search.get('page')) || 1))
  const setShownPage = (n: number) => setSearch((prev) => {
    const next = new URLSearchParams(prev)
    if (n > 1) next.set('page', String(n)); else next.delete('page')
    return next
  }, { replace: true })

  return (
    <Layout title={t('logs.title')} back={{ href: '/', label: t('logs.floorplan') }}>
      <PageHead title={t('logs.title')} desc={t(syslog ? 'logs.intro' : store ? 'logs.intros.store' : `logs.intros.${source}`)}
        actions={<Switch label={live && browsing ? t('logs.livePaused') : t('logs.live')} checked={live}
          title={live && browsing ? t('logs.livePausedWhy') : undefined} onChange={(e) => setLive(e.currentTarget.checked)} />} />
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} mb="md" />
      {syslog && data?.status.error && <Alert color="warn" mb="md">{data.status.error}</Alert>}
      {sources.length > 1 && (
        <SegmentedControl mb="sm" value={source} onChange={(v) => setSource(v as LogSource)} aria-label={t('logs.source')}
          data={sources.map((s) => ({ value: s, label: s.startsWith('plugin:') ? storeName(s) : t(`logs.sources.${s}`) }))} />
      )}
      {store ? (
        <Group gap="sm" mb="sm" align="flex-end" wrap="wrap">
          <TextInput label={QUERY[source.slice('plugin:'.length)] ? t('logs.queryIn', { language: QUERY[source.slice('plugin:'.length)].language }) : t('logs.query')}
            placeholder={QUERY[source.slice('plugin:'.length)]?.example} value={draft} styles={{ input: { fontFamily: 'var(--mantine-font-family-monospace)' } }}
            style={{ flex: '3 1 320px' }} onChange={(e) => setDraft(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') setLogql(draft.trim()) }} />
          <Select label={t('logs.range')} value={hours} onChange={(v) => setHours(v ?? '24')} allowDeselect={false}
            data={['1', '24', '168', '720'].map((h) => ({ value: h, label: t(`logs.hours.${h}`) }))} style={{ flex: '0 1 140px' }} />
          <Button onClick={() => setLogql(draft.trim())}>{t('logs.run')}</Button>
        </Group>
      ) : (
        <Group gap="sm" mb="sm" align="flex-end" wrap="wrap">
          <TextInput label={t('logs.search')} placeholder={t('logs.searchHint')} value={filters.q} style={{ flex: '2 1 220px' }}
            leftSection={<IconSearch size={16} />} type="search"
            onChange={(e) => set('q')(e.currentTarget.value)} />
          {syslog && (
            <>
              <Select label={t('logs.device')} placeholder={t('logs.all')} data={data?.status.devices ?? []} value={filters.device || null}
                onChange={set('device')} clearable searchable style={{ flex: '1 1 160px' }} />
              <EntitySelect kind="seats" label={t('logs.seatFilter')} placeholder={t('logs.all')} value={filters.seat}
                style={{ flex: '0 1 130px' }} onChange={set('seat')} />
              <EntitySelect kind="ports" switchName={filters.device} showUsed label={t('logs.port')} placeholder={t('logs.all')}
                value={filters.port} style={{ flex: '0 1 140px' }} onChange={set('port')} />
            </>
          )}
          <Select label={t('logs.severity')} placeholder={t('logs.all')} value={filters.severity || null} onChange={set('severity')} clearable
            data={SEVERITIES.slice(0, -1).map((s) => ({ value: s, label: t('logs.atLeast', { level: t(`logs.sev.${s}`) }) }))}
            style={{ flex: '1 1 160px' }} />
          {filtered && <Button variant="default" onClick={() => setFilters(EMPTY)}>{t('logs.clear')}</Button>}
        </Group>
      )}
      {store && data?.status.query_error && <Alert color="warn" mb="md">{data.status.query_error}</Alert>}
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : (
        <>
          {syslog && <StatusLine status={data.status} />}
          {syslog && !data.status.enabled && !data.status.demo && data.status.lines === 0 ? (
            <Alert color="gray" variant="light">{t('logs.off')} <Anchor href={DOCS}>docs/syslog.md</Anchor></Alert>
          ) : lines.length === 0 ? (
            <Text size="sm" c="dimmed">{filtered ? t('logs.noMatch') : t(syslog ? 'logs.none' : 'logs.noneHere')}</Text>
          ) : (
            <>
              {phone ? (
                <>
                  <ul className="fb-log-lines" aria-label={t('logs.title')}>
                    {lines.slice((shownPage - 1) * PAGE_SIZE, shownPage * PAGE_SIZE)
                      .map((l, i) => <Compact key={store ? `${l.id}-${i}` : l.id} line={l} onDevice={onDevice} />)}
                  </ul>
                  {pageCount > 1 && (
                    <Group justify="center" mt="sm">
                      <Pagination size="sm" total={pageCount} value={shownPage} onChange={setShownPage}
                        getControlProps={(control) => ({ 'aria-label': t(`table.${control}`) })} />
                    </Group>
                  )}
                </>
              ) : (
                <LogTable lines={lines} store={!!store} source={source} onDevice={onDevice} />
              )}
              {more && lines.length >= PAGE && shownPage === pageCount && (
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
