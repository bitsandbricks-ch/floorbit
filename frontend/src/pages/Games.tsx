import { Alert, Anchor, Group, Loader, Paper, SegmentedControl, SimpleGrid, Table, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { CacheRow, GamesData, LancacheData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { bytes } from './traffic/format'

const W = 1000
const H = 140
const RANGES = [6, 24, 168]
const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/games.md'
const pct = (n: number | null | undefined) => (n == null ? '–' : `${Math.round(n * 100)} %`)
const ratio = (hit: number, miss: number) => (hit + miss ? hit / (hit + miss) : null)

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper withBorder radius="lg" p="sm">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={700} size="xl">{value}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </Paper>
  )
}

/** Bytes the cache served per hour: from disk at the bottom, from the internet on top. */
function CacheChart({ cache }: { cache: LancacheData }) {
  const { t, i18n } = useTranslation()
  const hours = cache.hours
  const top = Math.max(1, ...hours.map((h) => h.hit_bytes + h.miss_bytes))
  const w = W / Math.max(1, hours.length)
  const stamp = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <section className="fb-stats-panel wide" aria-labelledby="games-cache">
      <Group justify="space-between" mb={6}>
        <h2 id="games-cache">{t('games.cachePerHour')}</h2>
        <Group gap="sm">
          <Text size="xs" c="dimmed"><span className="fb-dns-key hit" /> {t('games.hit')}</Text>
          <Text size="xs" c="dimmed"><span className="fb-dns-key miss" /> {t('games.miss')}</Text>
        </Group>
      </Group>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="fb-dns-chart" role="img"
        aria-label={t('games.chartLabel', { hit: bytes(cache.hit_bytes), miss: bytes(cache.miss_bytes) })}>
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

function Launchers({ data }: { data: GamesData }) {
  const { t, i18n } = useTranslation()
  const num = (n: number | null) => (n == null ? '–' : n.toLocaleString(i18n.language))
  return (
    <section className="fb-stats-panel wide" aria-labelledby="games-launchers">
      <h2 id="games-launchers">{t('games.launchers')}</h2>
      {data.launchers.length === 0 ? <Text size="sm" c="dimmed">{t('games.noLaunchers')}</Text> : (
        <Table.ScrollContainer minWidth={620}>
          <Table striped withRowBorders={false} verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('games.launcher')}</Table.Th>
                {data.sources.cache && <Table.Th>{t('games.fromCache')}</Table.Th>}
                {data.sources.traffic && <Table.Th>{t('games.traffic')}</Table.Th>}
                {data.sources.dns && <Table.Th>{t('games.lookups')}</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.launchers.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td fw={600}>{l.name}</Table.Td>
                  {data.sources.cache && (
                    <Table.Td>
                      {l.cache_hit_bytes == null ? '–' : (
                        <>{bytes((l.cache_hit_bytes ?? 0) + (l.cache_miss_bytes ?? 0))}
                          <Text span size="xs" c="dimmed"> · {t('games.ratio', { pct: pct(ratio(l.cache_hit_bytes ?? 0, l.cache_miss_bytes ?? 0)) })}</Text></>
                      )}
                    </Table.Td>
                  )}
                  {data.sources.traffic && (
                    <Table.Td>
                      {l.traffic_bytes == null ? '–' : (
                        <>{bytes(l.traffic_bytes)}<Text span size="xs" c="dimmed"> · {t('games.seats', { count: l.traffic_seats ?? 0 })}</Text></>
                      )}
                    </Table.Td>
                  )}
                  {data.sources.dns && (
                    <Table.Td>
                      {num(l.lookups)}
                      {!!l.dns_seats_max && <Text span size="xs" c="dimmed"> · {t('games.upTo', { count: l.dns_seats_max })}</Text>}
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Text size="xs" c="dimmed" mt={6}>{t('games.launchersText', { count: data.min_seats.dns })}</Text>
    </section>
  )
}

function Caches({ caches }: { caches: CacheRow[] }) {
  const { t } = useTranslation()
  return (
    <section className="fb-stats-panel" aria-labelledby="games-other">
      <h2 id="games-other">{t('games.otherCaches')}</h2>
      <ol className="fb-stats-top">
        {caches.map((c) => (
          <li key={c.cache}>
            <span className="name">{t(`games.cacheName.${c.cache}`, { defaultValue: c.cache })}
              <br /><small>{t('games.ratio', { pct: pct(ratio(c.hit_bytes, c.miss_bytes)) })}</small></span>
            <span className="value">{bytes(c.hit_bytes + c.miss_bytes)}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Board({ data }: { data: GamesData }) {
  const { t } = useTranslation()
  const c = data.cache
  return (
    <>
      {data.sources.cache && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
          <Figure label={t('games.servedLocally')} value={bytes(c.hit_bytes)} sub={t('games.servedLocallySub')} />
          <Figure label={t('games.fromInternet')} value={bytes(c.miss_bytes)} sub={t('games.fromInternetSub')} />
          <Figure label={t('games.hitRatio')} value={pct(c.hit_ratio)} sub={t('games.hitRatioSub')} />
        </SimpleGrid>
      )}
      <div className="fb-stats">
        {data.sources.cache && <CacheChart cache={c} />}
        <Launchers data={data} />
        {data.games.length > 0 && (
          <section className="fb-stats-panel" aria-labelledby="games-games">
            <h2 id="games-games">{t('games.games')}</h2>
            <ol className="fb-stats-top">
              {data.games.map((g) => (
                <li key={g.name}>
                  <span className="name">{g.name} <small>· {t('games.seats', { count: g.seats })}</small></span>
                  <span className="value">{bytes(g.bytes)}</span>
                </li>
              ))}
            </ol>
            <Text size="xs" c="dimmed" mt={6}>{t('games.gamesText')}</Text>
          </section>
        )}
        {data.other_caches.length > 0 && <Caches caches={data.other_caches} />}
      </div>
    </>
  )
}

/** What the hall plays and downloads, and what the LAN cache saved (issue #88). Hall-wide only. */
export default function Games() {
  const { t } = useTranslation()
  const [hours, setHours] = useState(24)
  const query = useQuery({ queryKey: qk.games(hours), queryFn: () => get<GamesData>(`/api/games?hours=${hours}`), refetchInterval: 60_000 })
  const data = query.data
  const none = data && !data.sources.dns && !data.sources.traffic && !data.sources.cache
  return (
    <Layout title={t('games.title')} back={{ href: '/traffic', label: t('games.trafficPage') }}>
      <PageHead title={t('games.title')} desc={t('games.intro')}
        actions={
          <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('games.range')}
            data={RANGES.map((h) => ({ value: String(h), label: t(`games.hours.${h}`) }))} />
        } />
      {query.error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: query.error.message })}</Alert>}
      {data?.cache.error && <Alert color="warn" mb="md">{t('games.cacheError', { message: data.cache.error })}</Alert>}
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : none ? (
        <Alert color="gray" variant="light">{t('games.noSources')} <Anchor href={DOCS}>docs/games.md</Anchor></Alert>
      ) : (
        <>
          <Text size="sm" c="dimmed" mb="sm">
            {[data.sources.cache && t('games.fromCacheSource'), data.sources.traffic && t('games.fromTrafficSource'),
              data.sources.dns && t('games.fromDnsSource')].filter(Boolean).join(' · ')}
          </Text>
          <Board data={data} />
        </>
      )}
    </Layout>
  )
}
