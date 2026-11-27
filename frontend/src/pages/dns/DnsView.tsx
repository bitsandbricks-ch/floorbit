import { Alert, Anchor, Badge, Group, SegmentedControl, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { DnsData, DnsSite } from '@/api/types'
import type { ViewProps } from '@/pages/monitoring/pages'
import { Card, type DataColumn, DataTable, ErrorBanner, LoadingState, StatGrid, StatTile } from '@bitsandbricks/ui'
import { clock, dayClock } from '@/lib/time'
import './DnsView.css'

const W = 1000
const H = 140
const RANGES = [6, 24, 168]
const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/dns.md'
// Small panels page at 10 rows so they stay side by side; the long list of sites at 50 (handbook).
const PANEL_ROWS = 10
const SITE_ROWS = 50


/** Lookups per hour as bars, the blocked part in red on top. */
function Chart({ hours, label }: { hours: DnsData['hours']; label: string }) {
  const { t, i18n } = useTranslation()
  const top = Math.max(1, ...hours.map((h) => h.lookups))
  const w = W / Math.max(1, hours.length)
  const stamp = (ts: number) => dayClock(ts, i18n.language)
  return (
    <Card heading={2} className="fb-wide" title={t('dns.perHour')} actions={<>
      <Group gap="sm">
        <Text size="xs" c="dimmed"><span className="fb-dns-key" /> {t('dns.answered')}</Text>
        <Text size="xs" c="dimmed"><span className="fb-dns-key blocked" /> {t('dns.blockedKey')}</Text>
      </Group>
    </>}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-dns-chart" role="img" aria-label={label}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} className="grid" x1={0} x2={W} y1={H * f} y2={H * f} />)}
        {hours.map((h, i) => {
          const all = (h.lookups / top) * H
          const blocked = (h.blocked / top) * H
          return (
            <g key={h.t}>
              <rect className="ok" x={i * w + w * 0.1} width={w * 0.8} y={H - all} height={all - blocked} />
              <rect className="blocked" x={i * w + w * 0.1} width={w * 0.8} y={H - all + (all - blocked)} height={blocked} />
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
    </Card>
  )
}

/** The few sites of the small view: a plain top list. */
function TopList({ sites, value }: { sites: DnsSite[]; value: (s: DnsSite) => string }) {
  const { t } = useTranslation()
  return (
    <ol className="fb-stats-top">
      {sites.map((s) => (
        <li key={s.site}>
          <span className="name">{s.site} <Badge size="xs" variant="light" color="gray" tt="none">{t(`dns.cat.${s.category}`)}</Badge></span>
          <span className="value">{value(s)}</span>
        </li>
      ))}
    </ol>
  )
}

/** One panel of the page: a heading over a list or a sortable, paged table. */
function DnsCard({ title, wide, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return (
    <Card heading={2} className={wide ? 'fb-wide' : undefined} title={title}>
      {children}
    </Card>
  )
}

function siteColumns(t: (k: string, o?: Record<string, unknown>) => string, value: DataColumn<DnsSite>): DataColumn<DnsSite>[] {
  return [
    { id: 'site', header: t('dns.site'), cell: (s) => s.site, sort: (s) => s.site, wrap: true },
    { id: 'category', header: t('dns.category'), sort: (s) => t(`dns.cat.${s.category}`), hideOnPhone: true,
      cell: (s) => <Badge size="xs" variant="light" color="gray" tt="none">{t(`dns.cat.${s.category}`)}</Badge> },
    value,
  ]
}

function Board({ data, compact }: { data: DnsData; compact: boolean }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  const catTop = Math.max(1, ...data.categories.map((c) => c.lookups))
  const lookups: DataColumn<DnsSite> = { id: 'lookups', header: t('dns.lookups'), numeric: true, descFirst: true,
    sort: (s) => s.lookups, cell: (s) => num(s.lookups) }
  const clients: DataColumn<DnsSite> = { id: 'clients', header: t('dns.seats'), numeric: true, descFirst: true, hideOnPhone: true,
    sort: (s) => s.clients_max, cell: (s) => num(s.clients_max) }
  const blocked: DataColumn<DnsSite> = { id: 'blocked', header: t('dns.blocked'), numeric: true, descFirst: true,
    sort: (s) => s.blocked, cell: (s) => num(s.blocked) }
  const seen: DataColumn<DnsSite> = { id: 'seen', header: t('dns.firstSeen'), numeric: true, descFirst: true,
    sort: (s) => s.first_seen ?? 0, cell: (s) => clock(s.first_seen ?? 0, i18n.language) }
  const table = { urlState: false, bare: true, density: 'compact' as const, rowKey: (s: DnsSite) => s.site }
  return (
    <>
      <StatGrid style={{ marginBottom: 'var(--mantine-spacing-md)' }}>
        <StatTile label={t('dns.lookups')} value={num(data.lookups)} />
        <StatTile label={t('dns.blocked')} value={num(data.blocked)}
          sub={data.block_share != null ? t('dns.share', { pct: (data.block_share * 100).toFixed(1) }) : undefined} />
        <StatTile label={t('dns.named')} value={num(data.named)} sub={t('dns.namedSub', { count: data.min_clients })} />
        <StatTile label={t('dns.unnamed')} value={num(data.unnamed_lookups)} sub={t('dns.unnamedSub')} />
      </StatGrid>
      <div className="fb-stats">
        <Chart hours={data.hours} label={t('dns.chartLabel', { lookups: num(data.lookups), blocked: num(data.blocked) })} />
        {compact ? (
          <DnsCard title={t('dns.top')}>
            {data.sites.length === 0 ? <Text size="sm" c="dimmed">{t('dns.noneYet', { count: data.min_clients })}</Text>
              : <TopList sites={data.sites.slice(0, 5)} value={(s) => num(s.lookups)} />}
          </DnsCard>
        ) : (
          <>
            <DnsCard title={t('dns.categories')}>
              <DataTable {...table} rowKey={(c) => c.id} label={t('dns.categories')} rows={data.categories} pageSize={PANEL_ROWS}
                defaultSort={{ id: 'lookups', desc: true }} empty={<Text size="sm" c="dimmed">{t('dns.noneYet', { count: data.min_clients })}</Text>}
                columns={[
                  { id: 'category', header: t('dns.category'), cell: (c) => t(`dns.cat.${c.id}`), sort: (c) => t(`dns.cat.${c.id}`) },
                  { id: 'share', header: '', width: '40%', hideOnPhone: true,
                    cell: (c) => <span className="fb-dns-bar" aria-hidden="true"><i style={{ width: `${(c.lookups / catTop) * 100}%` }} /></span> },
                  { id: 'lookups', header: t('dns.lookups'), numeric: true, descFirst: true, sort: (c) => c.lookups, cell: (c) => num(c.lookups) },
                ]} />
              <Text size="xs" c="dimmed" mt={6}>{t('dns.categoriesText')}</Text>
            </DnsCard>
            <DnsCard title={t('dns.blockedSites')}>
              <DataTable {...table} label={t('dns.blockedSites')} rows={data.blocked_sites} pageSize={PANEL_ROWS} columns={siteColumns(t, blocked)}
                defaultSort={{ id: 'blocked', desc: true }} empty={<Text size="sm" c="dimmed">{t('dns.noneBlocked')}</Text>} />
            </DnsCard>
            <DnsCard title={t('dns.top')} wide>
              <DataTable {...table} label={t('dns.top')} rows={data.sites} pageSize={SITE_ROWS} columns={siteColumns(t, lookups).concat(clients)}
                defaultSort={{ id: 'lookups', desc: true }} empty={<Text size="sm" c="dimmed">{t('dns.noneYet', { count: data.min_clients })}</Text>} />
            </DnsCard>
            <DnsCard title={t('dns.new')} wide>
              <DataTable {...table} label={t('dns.new')} rows={data.new} pageSize={PANEL_ROWS} columns={siteColumns(t, seen)}
                defaultSort={{ id: 'seen', desc: true }} empty={<Text size="sm" c="dimmed">{t('dns.noneNew')}</Text>} />
            </DnsCard>
          </>
        )}
      </div>
    </>
  )
}

/** What the hall looks up, from the event's DNS resolver (issue #87). Hall-wide only: a site is
 *  named once enough different seats looked it up, and nothing is kept per seat. */
export default function DnsView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const [hours, setHours] = useState(24)
  const query = useQuery({ queryKey: qk.dns(hours), queryFn: () => get<DnsData>(`/api/dns?hours=${hours}`), refetchInterval: 60_000 })
  const data = query.data
  return (
    <>
      {expanded && (
        <Group justify="space-between" mb="sm" wrap="wrap">
          <Text size="sm" c="dimmed">{data ? t('dns.privacy', { count: data.min_clients }) : ''}</Text>
          <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('dns.range')}
            data={RANGES.map((h) => ({ value: String(h), label: t(`dns.hours.${h}`) }))} />
        </Group>
      )}
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} mb="md" />
      {data?.error && <Alert color="warn" mb="md">{t('dns.pluginError', { message: data.error })}</Alert>}
      {query.isPending || !data ? <LoadingState lines={!expanded} /> : data.plugins === 0 && data.lookups === 0 ? (
        <Alert color="gray" variant="light">{t('dns.noPlugin')} <Anchor href={DOCS}>docs/dns.md</Anchor></Alert>
      ) : <Board data={data} compact={!expanded} />}
    </>
  )
}
