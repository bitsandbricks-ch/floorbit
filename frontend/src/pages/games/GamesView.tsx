import { Alert, Anchor, Group, Loader, SegmentedControl, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { GamesData } from '@/api/types'
import type { ViewProps } from '@/pages/monitoring/pages'
import { Card, DataTable, ErrorBanner } from '@bitsandbricks/ui'
import { bytes } from '../traffic/format'
import { RANGES } from './ranges'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/games.md'
const pct = (n: number | null | undefined) => (n == null ? '–' : `${Math.round(n * 100)} %`)
const ratio = (hit: number, miss: number) => (hit + miss ? hit / (hit + miss) : null)

type Launcher = GamesData['launchers'][number]

function Launchers({ data }: { data: GamesData }) {
  const { t, i18n } = useTranslation()
  const num = (n: number | null) => (n == null ? '–' : n.toLocaleString(i18n.language))
  return (
    <Card heading={2} className="fb-wide" title={t('games.launchers')}>
      {data.launchers.length === 0 ? <Text size="sm" c="dimmed">{t('games.noLaunchers')}</Text> : (
        <DataTable rows={data.launchers} rowKey={(l) => l.id} label={t('games.launchers')} urlState={false} pageSize={0} bare striped
          density="compact" minWidth={620} defaultSort={{ id: data.sources.cache ? 'cache' : data.sources.traffic ? 'traffic' : 'launcher', desc: !!(data.sources.cache || data.sources.traffic) }}
          columns={[
            { id: 'launcher', header: t('games.launcher'), sort: (l) => l.name, cell: (l) => <Text span fw={600} inherit>{l.name}</Text> },
            ...(data.sources.cache ? [{ id: 'cache', header: t('games.fromCache'), descFirst: true,
              sort: (l: Launcher) => (l.cache_hit_bytes == null ? -1 : (l.cache_hit_bytes ?? 0) + (l.cache_miss_bytes ?? 0)),
              cell: (l: Launcher) => (l.cache_hit_bytes == null ? '–' : (
                <>{bytes((l.cache_hit_bytes ?? 0) + (l.cache_miss_bytes ?? 0))}
                  <Text span size="xs" c="dimmed"> · {t('games.ratio', { pct: pct(ratio(l.cache_hit_bytes ?? 0, l.cache_miss_bytes ?? 0)) })}</Text></>
              )) }] : []),
            ...(data.sources.traffic ? [{ id: 'traffic', header: t('games.traffic'), descFirst: true, sort: (l: Launcher) => l.traffic_bytes ?? -1,
              cell: (l: Launcher) => (l.traffic_bytes == null ? '–' : (
                <>{bytes(l.traffic_bytes)}<Text span size="xs" c="dimmed"> · {t('games.seats', { count: l.traffic_seats ?? 0 })}</Text></>
              )) }] : []),
            ...(data.sources.dns ? [{ id: 'lookups', header: t('games.lookups'), descFirst: true, sort: (l: Launcher) => l.lookups ?? -1,
              cell: (l: Launcher) => (
                <>{num(l.lookups)}{!!l.dns_seats_max && <Text span size="xs" c="dimmed"> · {t('games.upTo', { count: l.dns_seats_max })}</Text>}</>
              ) }] : []),
          ]} />
      )}
      <Text size="xs" c="dimmed" mt={6}>{t('games.launchersText', { count: data.min_seats.dns })}</Text>
    </Card>
  )
}

/** Games by title: the most seats any source saw, and where it was seen (issue #1481). */
function Titles({ data, compact }: { data: GamesData; compact: boolean }) {
  const { t } = useTranslation()
  const rows = data.titles.filter((g) => g.seats > 0 || (g.cache_hit_bytes ?? 0) + (g.cache_miss_bytes ?? 0) > 0)
  const seen = (g: Launcher) => [g.dns_seats_max && t('games.via.dns'), g.traffic_seats && t('games.via.traffic'),
    g.players && t('games.via.servers'), g.cache_hit_bytes != null && t('games.via.cache')].filter(Boolean).join(' + ')
  return (
    <Card heading={2} title={t('games.titles')}
      actions={!compact ? <Anchor component={Link} to="/applications" size="sm">{t('games.manage')}</Anchor> : undefined}>
      {rows.length === 0 ? <Text size="sm" c="dimmed">{t('games.noTitles')}</Text> : (
        <ol className="fb-stats-top">
          {rows.slice(0, compact ? 8 : undefined).map((g) => (
            <li key={g.id}>
              <span className="name">{g.name} <small>· {seen(g)}</small></span>
              <span className="value">{g.seats ? t('games.seats', { count: g.seats }) : bytes((g.cache_hit_bytes ?? 0) + (g.cache_miss_bytes ?? 0))}</span>
            </li>
          ))}
        </ol>
      )}
      <Text size="xs" c="dimmed" mt={6}>{t('games.titlesText', { count: data.min_seats.dns })}</Text>
    </Card>
  )
}

function Board({ data, compact, embedded }: { data: GamesData; compact: boolean; embedded: boolean }) {
  const { t } = useTranslation()
  const c = data.cache
  return (
    <>
      {/* The cache's own numbers live on the LAN cache page (#1420); here only what each game fetched. */}
      {data.sources.cache && !embedded && (
        <Text size="sm" c="dimmed" mb="md">
          {t('games.cacheLink', { saved: bytes(c.hit_bytes) })} <Anchor href="/lancache">{t('games.cacheLinkOpen')}</Anchor>
        </Text>
      )}
      <div className="fb-stats">
        <Titles data={data} compact={compact} />
        {!compact && <Launchers data={data} />}
        {data.games.length > 0 && (
          <Card heading={2} title={t('games.games')}>
            <ol className="fb-stats-top">
              {data.games.slice(0, compact ? 8 : undefined).map((g) => (
                <li key={g.name}>
                  <span className="name">{g.name} <small>· {t('games.seats', { count: g.seats })}</small></span>
                  <span className="value">{bytes(g.bytes)}</span>
                </li>
              ))}
            </ol>
            <Text size="xs" c="dimmed" mt={6}>{t('games.gamesText')}</Text>
          </Card>
        )}
      </div>
    </>
  )
}

/** What the hall plays and downloads, and what the LAN cache saved (issue #88). Hall-wide only. */
export default function GamesView({ expanded, hours: given }: ViewProps & { hours?: number }) {
  const { t } = useTranslation()
  const [own, setHours] = useState(24)
  // On Traffic > Games and downloads the page picks the range and shows the LAN cache below (#1642).
  const embedded = given != null
  const hours = given ?? own
  const query = useQuery({ queryKey: qk.games(hours), queryFn: () => get<GamesData>(`/api/games?hours=${hours}`), refetchInterval: 60_000 })
  const data = query.data
  const none = data && !data.sources.dns && !data.sources.traffic && !data.sources.cache && !data.sources.servers
  return (
    <>
      {expanded && (
        <Group justify="space-between" mb="sm" wrap="wrap">
          <Text size="sm" c="dimmed">
            {data ? [data.sources.cache && t('games.fromCacheSource'), data.sources.traffic && t('games.fromTrafficSource'),
              data.sources.dns && t('games.fromDnsSource')].filter(Boolean).join(' · ') : ''}
          </Text>
          {!embedded && (
            <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('games.range')}
              data={RANGES.map((h) => ({ value: String(h), label: t(`games.hours.${h}`) }))} />
          )}
        </Group>
      )}
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} mb="md" />
      {data?.cache.error && <Alert color="warn" mb="md">{t('games.cacheError', { message: data.cache.error })}</Alert>}
      {query.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : none ? (
        <Alert color="gray" variant="light">{t('games.noSources')} <Anchor href={DOCS}>docs/games.md</Anchor></Alert>
      ) : <Board data={data} compact={!expanded} embedded={embedded} />}
    </>
  )
}
