import { Paper, Text, Title } from '@mantine/core'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { FeedFailed, PageOff, StaleNote } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'
import { readBoot } from '@/nav/boot'
import { isScreen, usePublicFeed } from '@/lib/publicFeed'
import { clock } from '@/lib/time'
import { BITS, BYTES, scaled } from '@/lib/units'

export type WallFacts = {
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

/** The public stats wall (issue #105, docs/stats-wall.md): hall-wide numbers for a big screen
 *  (``?screen=1``: larger type, no scrolling) or attendees' phones. No account; no names, seats or
 *  addresses, only what /wall.json gives. */
export default function PublicWall() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const screen = isScreen()
  const feed = usePublicFeed<WallFacts>('/wall.json', 60)
  const title = t('publicWall.title')
  const event = readBoot().brand.name
  useEffect(() => { if (screen) document.title = `${title} · Floorbit` }, [screen, title])
  const f = feed.data
  let body
  if (feed.off) body = <PageOff title={title} text={t('publicWall.off')} />
  else if (feed.failed) body = <FeedFailed title={title} onRetry={feed.retry} />
  else if (!f) body = <Paper withBorder radius="lg" p="lg" mih={160} aria-busy="true" />
  else {
    const empty = !f.online && !f.downloaded && !f.peak && !f.games?.length
    const of = t('publicWall.of', { n: f.seats })
    body = (
      <>
        <header className="fb-wall-head">
          <Title order={1} className="fb-wall-title">{event || title}</Title>
          {event && <Text c="dimmed">{title}</Text>}
        </header>
        {empty ? (
          <Paper withBorder radius="lg" p="lg"><Text>{t('publicWall.nothing')}</Text></Paper>
        ) : (
          <section className="fb-wall-grid" aria-label={title}>
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
            {!!f.online_max && <Fact tone="up" title={t('publicWall.onlineMax')} value={String(f.online_max)} note={of} />}
            {f.busiest_hour && (
              <Fact tone="bit" title={t('publicWall.busiest')} value={clock(f.busiest_hour.t)}
                note={t('publicWall.avg', { rate: scaled(f.busiest_hour.bps, BITS, lang).join(' ') })} />
            )}
            {f.loyal_block && (
              <Fact id="wall-loyal" tone="trace" title={t('publicWall.loyal')} value={[String(Math.round(f.loyal_block.share * 100)), '%']}
                note={t('publicWall.loyalDetail', { name: f.loyal_block.name, hours: f.loyal_block.hours.toLocaleString(lang) })} />
            )}
            {!!f.cache_saved && (
              <Fact tone="up" title={t('publicWall.cache')} value={scaled(f.cache_saved, BYTES, lang)} note={t('publicWall.cacheDetail')} />
            )}
            {!!f.games?.length && (
              <Paper withBorder radius="lg" className="fb-wall-fact fb-wall-k-bit fb-wall-games" id="wall-games">
                <Title order={2} className="fb-wall-label">{t('publicWall.games')}</Title>
                <ol>
                  {f.games.map((g, i) => (
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
      </>
    )
  }
  const stale = feed.stale && <StaleNote since={feed.lastGood} />
  // The big screen: the numbers alone, edge to edge; the attribution would only take room there.
  if (screen) return <main className="fb-wall fb-wall--screen">{stale}{body}</main>
  return <PublicPage title={title} size="board">{stale}<div className="fb-wall">{body}</div></PublicPage>
}
