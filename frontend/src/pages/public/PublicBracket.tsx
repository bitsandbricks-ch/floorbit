import { Chip, Group, Paper, Text, Title } from '@mantine/core'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { FeedFailed, PageOff, StaleNote } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'
import { isScreen, usePublicFeed } from '@/lib/publicFeed'
import { clock } from '@/lib/time'

type Side = { name: string | null; score: number | null }
type Match = { id: string; a: Side; b: Side; status: 'open' | 'live' | 'done' | string; winner: 'a' | 'b' | null; station?: string }
type Round = { n: number; label: 'final' | 'semi' | 'quarter' | null; matches: Match[] }
export type PublicBracketData = { id: string; name: string; zone: string | null; champion: string | null; live?: number; rounds: Round[] }

function MatchBox({ m, first }: { m: Match; first: boolean }) {
  const { t } = useTranslation()
  return (
    <div className={`fb-pbr-match${m.status === 'live' ? ' fb-pbr-live' : ''}`} data-match={m.id}>
      {m.status === 'live' && <span className="fb-pbr-tag">{t('publicBracket.live')}</span>}
      {(['a', 'b'] as const).map((side) => {
        const team = m[side]
        const cls = [m.winner === side ? 'won' : m.winner ? 'lost' : '', team.name ? '' : 'tbd'].filter(Boolean).join(' ')
        return (
          <div key={side} className={`fb-pbr-team ${cls}`}>
            <span className="fb-pbr-name">{team.name || (first && m.winner ? t('publicBracket.bye') : t('publicBracket.tbd'))}</span>
            <span className="fb-pbr-score">{team.score ?? ''}</span>
          </div>
        )
      })}
      {m.station && <div className="fb-pbr-station">{m.station}</div>}
    </div>
  )
}

/** Public tournament brackets (issue #107, docs/tournament.md), for big screens (``?screen=1``)
 *  and phones; ``?id=`` picks the bracket. No account; reads /bracket.json every 30 seconds. */
export default function PublicBracket() {
  const { t } = useTranslation()
  const screen = isScreen()
  const [params, setParams] = useSearchParams()
  const feed = usePublicFeed<{ brackets: PublicBracketData[] }>('/bracket.json', 30)
  const all = feed.data?.brackets ?? []
  const b = all.find((x) => x.id === params.get('id')) ?? all[0]
  const title = b?.name ?? t('publicBracket.title')
  useEffect(() => { if (screen) document.title = `${title} · Floorbit` }, [screen, title])
  let body
  if (feed.off) body = <PageOff title={t('publicBracket.title')} text={t('publicBracket.off')} />
  else if (feed.failed) body = <FeedFailed title={t('publicBracket.title')} onRetry={feed.retry} />
  else if (!feed.data) body = <Paper withBorder radius="lg" p="lg" mih={160} aria-busy="true" />
  else if (!b) body = <><Title order={1} className="fb-wall-title">{t('publicBracket.title')}</Title><Text c="dimmed">{t('publicBracket.empty')}</Text></>
  else {
    body = (
      <>
        <header>
          <Title order={1} className="fb-wall-title">{b.name}</Title>
          {b.zone && <Text c="dimmed" size="sm">{b.zone}</Text>}
        </header>
        {all.length > 1 && !screen && (
          <Chip.Group value={b.id} onChange={(id) => setParams({ id: id as string }, { replace: true })}>
            <Group gap={6} role="radiogroup" aria-label={t('publicBracket.title')}>
              {all.map((x) => <Chip key={x.id} value={x.id} size="sm">{x.name}</Chip>)}
            </Group>
          </Chip.Group>
        )}
        <div className="fb-pbr-scroll">
          <section className="fb-pbr" aria-label={b.name}>
            {b.rounds.map((r) => (
              <div key={r.n} className="fb-pbr-round">
                <h2>{r.label ? t(`publicBracket.${r.label}`) : t('publicBracket.round', { n: r.n })}</h2>
                <div className="fb-pbr-matches">
                  {r.matches.map((m) => <MatchBox key={m.id} m={m} first={r.n === 1} />)}
                </div>
              </div>
            ))}
            {b.champion && (
              <div className="fb-pbr-round">
                <h2>&nbsp;</h2>
                <div className="fb-pbr-matches">
                  <div className="fb-pbr-champion"><Text c="dimmed" size="sm">{t('publicBracket.champion')}</Text><b>{b.champion}</b></div>
                </div>
              </div>
            )}
          </section>
        </div>
        <Text size="sm" c="dimmed" className="fb-wall-note">
          {t('publicBracket.updated', { time: feed.lastGood ? clock(feed.lastGood / 1000) : '–' })}
        </Text>
      </>
    )
  }
  const stale = feed.stale && <StaleNote since={feed.lastGood} />
  if (screen) return <main className="fb-pbr-page fb-pbr-page--screen">{stale}{body}</main>
  return <PublicPage title={title} size="wide">{stale}<div className="fb-pbr-page">{body}</div></PublicPage>
}
