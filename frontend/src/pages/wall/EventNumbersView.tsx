import { Paper, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { FeedFailed, StaleNote } from '@/components/PublicFeedNotes'
import { usePublicFeed } from '@/lib/publicFeed'
import { clock } from '@/lib/time'
import { BITS, BYTES, scaled } from '@/lib/units'
import type { ViewProps } from '@/widgets/views'

type WallFacts = {
  online: number | null; seats: number; online_max?: number | null
  downloaded?: number | null; running_hours?: number | null
  peak?: { bps: number; at: number } | null
  busiest_hour?: { bps: number; t: number } | null
  loyal_block?: { name: string; share: number; hours: number } | null
  cache_saved?: number | null
  games?: { name: string; bar: number }[] | null
}

function Big({ value }: { value: [string, string] | string }) {
  if (typeof value === 'string') return <span className="fb-wall-big">{value}</span>
  return <span className="fb-wall-big">{value[0]}<small>{value[1]}</small></span>
}

function Fact({ id, tone, title, value, note }: {
  id?: string; tone: 'up' | 'warn' | 'trace' | 'bit'; title: string; value: [string, string] | string; note?: string
}) {
  return (
    <Paper withBorder radius="lg" className={`fb-wall-fact fb-wall-k-${tone}`} id={id}>
      <Title order={2} className="fb-wall-label">{title}</Title>
      <Big value={value} />
      {note && <Text className="fb-wall-note" c="dimmed">{note}</Text>}
    </Paper>
  )
}

/** The event in numbers (issue #105, docs/stats-wall.md): hall-wide facts for a public dashboard
 *  on a big screen. No names, seats or addresses, only what /wall.json gives, so it may show signed
 *  out. Off until Settings > Attendee pages turns the stats wall on. */
export default function EventNumbersView({ expanded }: ViewProps) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const feed = usePublicFeed<WallFacts>('/wall.json', 60)
  const f = feed.data
  if (feed.off) return <Text c="dimmed">{t('publicWall.off')}</Text>
  if (feed.failed) return <FeedFailed title={t('publicWall.title')} onRetry={feed.retry} />
  if (!f) return <Paper withBorder radius="lg" p="lg" mih={120} aria-busy="true" />
  const empty = !f.online && !f.downloaded && !f.peak && !f.games?.length
  const of = t('publicWall.of', { n: f.seats })
  return (
    <div className={`fb-wall${expanded ? ' fb-wall--screen' : ''}`}>
      {feed.stale && <StaleNote since={feed.lastGood} />}
      {empty ? <Text c="dimmed">{t('publicWall.nothing')}</Text> : (
        <section className="fb-wall-grid" aria-label={t('publicWall.title')}>
          <Fact id="wall-online" tone="up" title={t('publicWall.online')} value={f.online == null ? '–' : String(f.online)}
            note={f.online == null ? t('publicWall.unknown') : of} />
          {!!f.downloaded && (
            <Fact id="wall-downloaded" tone="trace" title={t('publicWall.downloaded')} value={scaled(f.downloaded, BYTES, lang)}
              note={f.running_hours ? t('publicWall.running', { n: Math.round(f.running_hours) }) : undefined} />
          )}
          {!!f.peak?.bps && (
            <Fact id="wall-peak" tone="warn" title={t('publicWall.peak')} value={scaled(f.peak.bps, BITS, lang)}
              note={t('publicWall.at', { time: clock(f.peak.at) })} />
          )}
          {expanded && !!f.online_max && <Fact tone="up" title={t('publicWall.onlineMax')} value={String(f.online_max)} note={of} />}
          {expanded && f.busiest_hour && (
            <Fact tone="bit" title={t('publicWall.busiest')} value={clock(f.busiest_hour.t)}
              note={t('publicWall.avg', { rate: scaled(f.busiest_hour.bps, BITS, lang).join(' ') })} />
          )}
          {expanded && f.loyal_block && (
            <Fact id="wall-loyal" tone="trace" title={t('publicWall.loyal')} value={[String(Math.round(f.loyal_block.share * 100)), '%']}
              note={t('publicWall.loyalDetail', { name: f.loyal_block.name, hours: f.loyal_block.hours.toLocaleString(lang) })} />
          )}
          {expanded && !!f.cache_saved && (
            <Fact tone="up" title={t('publicWall.cache')} value={scaled(f.cache_saved, BYTES, lang)} note={t('publicWall.cacheDetail')} />
          )}
          {!!f.games?.length && (
            <Paper withBorder radius="lg" className="fb-wall-fact fb-wall-k-bit fb-wall-games" id="wall-games">
              <Title order={2} className="fb-wall-label">{t('publicWall.games')}</Title>
              <ol>
                {f.games.slice(0, expanded ? undefined : 3).map((g, i) => (
                  <li key={g.name}>
                    <span className="fb-wall-n">{i + 1}</span>
                    <span>{g.name}</span>
                    <span className="fb-wall-bar" aria-hidden="true"><span style={{ width: `${Math.round(g.bar * 1000) / 10}%` }} /></span>
                  </li>
                ))}
              </ol>
            </Paper>
          )}
        </section>
      )}
      <Text size="sm" c="dimmed" className="fb-wall-note">
        {t('publicWall.privacy')} {t('publicWall.updated', { time: feed.lastGood ? clock(feed.lastGood / 1000) : '–' })}
      </Text>
    </div>
  )
}
