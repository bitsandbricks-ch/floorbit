import { Alert, Anchor, Badge, Group, Loader, Paper, SegmentedControl, SimpleGrid, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { DnsData, DnsSite } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const W = 1000
const H = 140
const RANGES = [6, 24, 168]
const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/dns.md'

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper withBorder radius="lg" p="sm">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={700} size="xl">{value}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </Paper>
  )
}

/** Lookups per hour as bars, the blocked part in red on top. */
function Chart({ hours, label }: { hours: DnsData['hours']; label: string }) {
  const { t, i18n } = useTranslation()
  const top = Math.max(1, ...hours.map((h) => h.lookups))
  const w = W / Math.max(1, hours.length)
  const stamp = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <section className="fb-stats-panel wide" aria-labelledby="dns-hours">
      <Group justify="space-between" mb={6}>
        <h2 id="dns-hours">{t('dns.perHour')}</h2>
        <Group gap="sm">
          <Text size="xs" c="dimmed"><span className="fb-dns-key" /> {t('dns.answered')}</Text>
          <Text size="xs" c="dimmed"><span className="fb-dns-key blocked" /> {t('dns.blockedKey')}</Text>
        </Group>
      </Group>
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
    </section>
  )
}

function Sites({ id, title, sites, empty, value, sub }: {
  id: string; title: string; sites: DnsSite[]; empty: string; value: (s: DnsSite) => string; sub?: (s: DnsSite) => string
}) {
  const { t } = useTranslation()
  return (
    <section className="fb-stats-panel" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {sites.length === 0 ? <Text size="sm" c="dimmed">{empty}</Text> : (
        <ol className="fb-stats-top">
          {sites.map((s) => (
            <li key={s.site}>
              <span className="name">{s.site} <Badge size="xs" variant="light" color="gray" tt="none">{t(`dns.cat.${s.category}`)}</Badge>
                {sub && <><br /><small>{sub(s)}</small></>}</span>
              <span className="value">{value(s)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Board({ data }: { data: DnsData }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  const catTop = Math.max(1, ...data.categories.map((c) => c.lookups))
  return (
    <>
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="md">
        <Figure label={t('dns.lookups')} value={num(data.lookups)} />
        <Figure label={t('dns.blocked')} value={num(data.blocked)}
          sub={data.block_share != null ? t('dns.share', { pct: (data.block_share * 100).toFixed(1) }) : undefined} />
        <Figure label={t('dns.named')} value={num(data.sites.length)} sub={t('dns.namedSub', { count: data.min_clients })} />
        <Figure label={t('dns.unnamed')} value={num(data.unnamed_lookups)} sub={t('dns.unnamedSub')} />
      </SimpleGrid>
      <div className="fb-stats">
        <Chart hours={data.hours} label={t('dns.chartLabel', { lookups: num(data.lookups), blocked: num(data.blocked) })} />
        <section className="fb-stats-panel" aria-labelledby="dns-categories">
          <h2 id="dns-categories">{t('dns.categories')}</h2>
          <ul className="fb-stats-bars">
            {data.categories.map((c) => (
              <li key={c.id}>
                <span>{t(`dns.cat.${c.id}`)}</span>
                <span className="bar"><i style={{ width: `${(c.lookups / catTop) * 100}%` }} /></span>
                <span className="value">{num(c.lookups)}</span>
              </li>
            ))}
          </ul>
          <Text size="xs" c="dimmed" mt={6}>{t('dns.categoriesText')}</Text>
        </section>
        <Sites id="dns-top" title={t('dns.top')} sites={data.sites.slice(0, 20)} empty={t('dns.noneYet', { count: data.min_clients })}
          value={(s) => num(s.lookups)} sub={(s) => t('dns.clients', { count: s.clients_max })} />
        <Sites id="dns-blocked" title={t('dns.blockedSites')} sites={data.blocked_sites} empty={t('dns.noneBlocked')}
          value={(s) => num(s.blocked)} />
        <Sites id="dns-new" title={t('dns.new')} sites={data.new} empty={t('dns.noneNew')}
          value={(s) => new Date((s.first_seen ?? 0) * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })} />
      </div>
    </>
  )
}

/** What the hall looks up, from the event's DNS resolver (issue #87). Hall-wide only: a site is
 *  named once enough different seats looked it up, and nothing is kept per seat. */
export default function Dns() {
  const { t } = useTranslation()
  const [hours, setHours] = useState(24)
  const query = useQuery({ queryKey: qk.dns(hours), queryFn: () => get<DnsData>(`/api/dns?hours=${hours}`), refetchInterval: 60_000 })
  const data = query.data
  return (
    <Layout title={t('dns.title')} back={{ href: '/traffic', label: t('dns.traffic') }}>
      <PageHead title={t('dns.title')} desc={t('dns.intro')}
        actions={
          <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('dns.range')}
            data={RANGES.map((h) => ({ value: String(h), label: t(`dns.hours.${h}`) }))} />
        } />
      {query.error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: query.error.message })}</Alert>}
      {data?.error && <Alert color="warn" mb="md">{t('dns.pluginError', { message: data.error })}</Alert>}
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : data.plugins === 0 && data.lookups === 0 ? (
        <Alert color="gray" variant="light">{t('dns.noPlugin')} <Anchor href={DOCS}>docs/dns.md</Anchor></Alert>
      ) : (
        <>
          <Text size="sm" c="dimmed" mb="sm">{t('dns.privacy', { count: data.min_clients })}</Text>
          <Board data={data} />
        </>
      )}
    </Layout>
  )
}
