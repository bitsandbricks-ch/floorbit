import { Alert, Anchor, Badge, Group, Loader, Paper, SegmentedControl, SimpleGrid, Stack, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { ActionResult, LancacheAgent, LancacheOverview } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { DataTable } from '@/components/DataTable'
import { StatTile } from '@/components/StatTile'
import { ErrorBanner } from '@/components/ui'
import { ago, dayClock } from '@/lib/time'
import type { ViewProps } from '@/pages/monitoring/pages'
import { bytes } from '../traffic/format'

const W = 1000
const H = 140
const RANGES = [6, 24, 168]
const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/lancache.md'
const pct = (n: number | null | undefined) => (n == null ? '–' : `${Math.round(n * 100)} %`)
const ratio = (hit: number, miss: number) => (hit + miss ? hit / (hit + miss) : null)

/** Bytes per hour: from the cache at the bottom, from the internet on top. */
function Chart({ data }: { data: LancacheOverview }) {
  const { t, i18n } = useTranslation()
  const hours = data.hours
  const top = Math.max(1, ...hours.map((h) => h.hit_bytes + h.miss_bytes))
  const w = W / Math.max(1, hours.length)
  const stamp = (ts: number) => dayClock(ts, i18n.language)
  return (
    <section className="fb-stats-panel wide" aria-labelledby="lc-hours">
      <Group justify="space-between" mb={6}>
        <h2 id="lc-hours">{t('lancache.perHour')}</h2>
        <Group gap="sm">
          <Text size="xs" c="dimmed"><span className="fb-dns-key hit" /> {t('lancache.hit')}</Text>
          <Text size="xs" c="dimmed"><span className="fb-dns-key miss" /> {t('lancache.miss')}</Text>
        </Group>
      </Group>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-dns-chart" role="img"
        aria-label={t('lancache.chartLabel', { hit: bytes(data.hit_bytes), miss: bytes(data.miss_bytes) })}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} className="grid" x1={0} x2={W} y1={H * f} y2={H * f} />)}
        {hours.map((h, i) => {
          const hit = (h.hit_bytes / top) * H
          const miss = (h.miss_bytes / top) * H
          return (
            <g key={h.t}>
              <rect className="hit" x={i * w + w * 0.1} width={w * 0.8} y={H - hit} height={hit} />
              <rect className="miss" x={i * w + w * 0.1} width={w * 0.8} y={H - hit - miss} height={miss} />
            </g>
          )
        })}
      </svg>
      {hours.length > 0 && (
        <Group justify="space-between">
          <Text size="xs" c="dimmed">{stamp(hours[0].t)}</Text>
          <Text size="xs" c="dimmed">{stamp(hours[hours.length - 1].t + 3600)}</Text>
        </Group>
      )}
    </section>
  )
}

function Check({ label, ok, text }: { label: string; ok: boolean | null; text: string }) {
  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <Badge variant="light" color={ok == null ? 'gray' : ok ? 'up' : 'warn'} miw={88}>{label}</Badge>
      <Text size="sm">{text}</Text>
    </Group>
  )
}

/** One agent's view of the cache machine: does it answer, does the DNS point at it, how full is it. */
function Machine({ agent }: { agent: LancacheAgent }) {
  const { t, i18n } = useTranslation()
  const beat = agent.heartbeat
  const dnsCheck = agent.dns_check
  const disk = agent.disk
  const health = agent.health
  const clearing = agent.clearing
  const used = disk?.total ? (disk.used ?? 0) / disk.total : null
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap={6}>
        <Group justify="space-between">
          <Text fw={600}>{agent.name ?? agent.id}</Text>
          <Text size="xs" c={agent.stale ? 'warn' : 'dimmed'}>
            {agent.stale ? t('lancache.stale', { when: ago(agent.updated, i18n.language) }) : t('lancache.updated', { when: ago(agent.updated, i18n.language) })}
          </Text>
        </Group>
        <Check label={t('lancache.heartbeat')} ok={beat ? beat.ok : null}
          text={!beat ? t('lancache.noHost') : beat.ok ? t('lancache.answers', { by: beat.processed_by ?? '', ms: beat.ms ?? 0 }) : beat.error ?? ''} />
        <Check label={t('lancache.dns')} ok={dnsCheck ? dnsCheck.ok : null}
          text={!dnsCheck ? t('lancache.noDnsCheck') : dnsCheck.ok ? t('lancache.dnsOk') : dnsCheck.error ?? ''} />
        <Check label={t('lancache.disk')} ok={!disk ? null : disk.error ? false : (used ?? 0) < 0.9}
          text={!disk ? t('lancache.noFolder') : disk.error ? disk.error
            : t('lancache.diskUsed', { used: bytes(disk.used ?? 0), total: bytes(disk.total ?? 0), pct: pct(used) })} />
        {health && health.status !== 'ok' && health.message && (
          <Check label={t('lancache.agent')} ok={false} text={health.message} />
        )}
        {clearing && (
          <Text size="xs" c="dimmed">
            {clearing.running ? t('lancache.clearing', { count: clearing.removed })
              : t('lancache.cleared', { count: clearing.removed, when: ago(clearing.finished ?? null, i18n.language) })}
          </Text>
        )}
      </Stack>
    </Paper>
  )
}

function Machines({ data, expanded }: { data: LancacheOverview; expanded: boolean }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const canClear = useCan('settings.manage')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const clear = useMutation({
    mutationFn: () => post<ActionResult>('/api/plugins/lancache/actions/clear_cache'),
    onSuccess: (r) => {
      setResult({ ok: true, text: r.message })
      void client.invalidateQueries({ queryKey: qk.lancacheAll })
    },
    onError: (e) => setResult({ ok: false, text: e.message }),
  })
  return (
    <section className="fb-stats-panel wide" aria-labelledby="lc-machine">
      <Group justify="space-between" mb={6}>
        <h2 id="lc-machine">{t('lancache.machine')}</h2>
        {expanded && canClear && data.agents.length > 0 && (
          <ConfirmButton size="xs" variant="light" danger label={t('lancache.clear')} question={t('lancache.clearQuestion')}
            loading={clear.isPending} onConfirm={() => clear.mutate()} />
        )}
      </Group>
      {result && <Alert color={result.ok ? 'up' : 'down'} variant="light" mb="sm" withCloseButton onClose={() => setResult(null)}>{result.text}</Alert>}
      {data.agents.length === 0 ? <Text size="sm" c="dimmed">{t('lancache.noAgent')}</Text> : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {data.agents.map((a) => <Machine key={a.id} agent={a} />)}
        </SimpleGrid>
      )}
    </section>
  )
}

function Downloads({ data }: { data: LancacheOverview }) {
  const { t } = useTranslation()
  const other = data.other_downloads
  return (
    <section className="fb-stats-panel wide" aria-labelledby="lc-downloads">
      <h2 id="lc-downloads">{t('lancache.downloads')}</h2>
      {data.downloads.length === 0 ? <Text size="sm" c="dimmed">{t('lancache.noDownloads', { count: data.min_clients })}</Text> : (
        <DataTable rows={data.downloads} rowKey={(d) => `${d.cache}/${d.item}`} label={t('lancache.downloads')} urlState={false} pageSize={25}
          bare striped density="compact" minWidth={560} defaultSort={{ id: 'bytes', desc: true }}
          columns={[
            { id: 'item', header: t('lancache.item'), mono: true, sort: (d) => d.item, cell: (d) => d.item },
            { id: 'service', header: t('lancache.service'), sort: (d) => d.cache, cell: (d) => t(`games.cacheName.${d.cache}`, { defaultValue: d.cache }) },
            { id: 'bytes', header: t('lancache.bytes'), numeric: true, descFirst: true, sort: (d) => d.hit_bytes + d.miss_bytes,
              cell: (d) => bytes(d.hit_bytes + d.miss_bytes) },
            { id: 'ratio', header: t('lancache.fromCache'), numeric: true, descFirst: true, sort: (d) => d.hit_ratio ?? -1, cell: (d) => pct(d.hit_ratio) },
            { id: 'players', header: t('lancache.players'), numeric: true, descFirst: true, sort: (d) => d.clients, cell: (d) => d.clients },
          ]} />
      )}
      <Text size="xs" c="dimmed" mt={6}>
        {t('lancache.downloadsText', { count: data.min_clients })}
        {other.items > 0 && ` ${t('lancache.otherDownloads', { items: other.items, size: bytes(other.hit_bytes + other.miss_bytes) })}`}
      </Text>
    </section>
  )
}

function Services({ data }: { data: LancacheOverview }) {
  const { t } = useTranslation()
  return (
    <section className="fb-stats-panel" aria-labelledby="lc-services">
      <h2 id="lc-services">{t('lancache.services')}</h2>
      {data.caches.length === 0 ? <Text size="sm" c="dimmed">{t('lancache.nothingYet')}</Text> : (
        <ol className="fb-stats-top">
          {data.caches.map((c) => (
            <li key={c.cache}>
              <span className="name">{t(`games.cacheName.${c.cache}`, { defaultValue: c.cache })}
                <br /><small>{t('lancache.ratio', { pct: pct(ratio(c.hit_bytes, c.miss_bytes)) })}</small></span>
              <span className="value">{bytes(c.hit_bytes + c.miss_bytes)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Suspects({ data }: { data: LancacheOverview }) {
  const { t } = useTranslation()
  return (
    <section className="fb-stats-panel" aria-labelledby="lc-suspects">
      <h2 id="lc-suspects">{t('lancache.suspects')}</h2>
      {data.suspects.length === 0 ? <Text size="sm" c="dimmed">{t('lancache.noSuspects')}</Text> : (
        <ol className="fb-stats-top">
          {data.suspects.map((s) => (
            <li key={`${s.cache}/${s.item}`}>
              <span className="name"><span style={{ fontFamily: 'monospace' }}>{s.item}</span>
                <br /><small>{t(`games.cacheName.${s.cache}`, { defaultValue: s.cache })} · {t('lancache.files', { count: s.files })}</small></span>
              <span className="value">{t('lancache.misses', { count: s.misses })}</span>
            </li>
          ))}
        </ol>
      )}
      <Text size="xs" c="dimmed" mt={6}>{t('lancache.suspectsText')}</Text>
    </section>
  )
}

function Lookups({ data }: { data: LancacheOverview }) {
  const { t, i18n } = useTranslation()
  if (data.dns_services.length === 0) return null
  return (
    <section className="fb-stats-panel" aria-labelledby="lc-dns">
      <h2 id="lc-dns">{t('lancache.lookups')}</h2>
      <ol className="fb-stats-top">
        {data.dns_services.map((s) => (
          <li key={s.cache}>
            <span className="name">{t(`games.cacheName.${s.cache}`, { defaultValue: s.cache })}</span>
            <span className="value">{s.lookups.toLocaleString(i18n.language)}</span>
          </li>
        ))}
      </ol>
      <Text size="xs" c="dimmed" mt={6}>{t('lancache.lookupsText')}</Text>
    </section>
  )
}

/** The LAN cache as a view (a dashboard pane, or a widget's expanded size): what it saved, the
 *  cache machine and, expanded, what the hall downloads and clearing it. Hall-wide only. */
export default function LancacheView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const [hours, setHours] = useState(24)
  const query = useQuery({
    queryKey: qk.lancache(hours),
    queryFn: () => get<LancacheOverview>(`/api/lancache?hours=${hours}`),
    refetchInterval: 30_000,
  })
  const data = query.data
  const peak = data?.clients.reduce((m, c) => Math.max(m, c.clients), 0) ?? 0
  return (
    <>
      {expanded && (
        <Group justify="flex-end" mb="sm">
          <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('lancache.range')}
            data={RANGES.map((h) => ({ value: String(h), label: t(`games.hours.${h}`) }))} />
        </Group>
      )}
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} mb="md" />
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : (
        <>
          {!data.plugin_on && (
            <Alert color="gray" variant="light" mb="md">
              {data.plugin_installed === false ? (
                <>
                  {t('lancache.pluginMissing')} <Anchor href="/settings/plugins?tab=marketplace">{t('lancache.marketplace')}</Anchor>
                </>
              ) : (
                <>
                  {t('lancache.pluginOff')} <Anchor href="/settings/plugins#pl-lancache">{t('lancache.pluginsPage')}</Anchor>
                </>
              )}{' '}
              · <Anchor href={DOCS}>docs/lancache.md</Anchor>
            </Alert>
          )}
          {data.error && <Alert color="warn" mb="md">{t('lancache.readError', { message: data.error })}</Alert>}
          <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
            <StatTile label={t('lancache.saved')} value={bytes(data.saved_bytes)} sub={t('lancache.savedSub')} />
            <StatTile label={t('lancache.hitRatio')} value={pct(data.hit_ratio)} sub={t('lancache.hitRatioSub')}
              tone={data.hit_ratio != null && data.hit_ratio < 0.5 ? 'warn' : undefined} />
            <StatTile label={t('lancache.fromInternet')} value={bytes(data.miss_bytes)} sub={t('lancache.fromInternetSub')} />
            <StatTile label={t('lancache.clients')} value={String(peak)} sub={t('lancache.clientsSub')} />
          </SimpleGrid>
          <div className="fb-stats">
            <Machines data={data} expanded={expanded} />
            {expanded && (
              <>
                <Chart data={data} />
                <Downloads data={data} />
                <Services data={data} />
                <Suspects data={data} />
                <Lookups data={data} />
              </>
            )}
          </div>
        </>
      )}
    </>
  )
}
