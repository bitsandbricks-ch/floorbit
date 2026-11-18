import { Anchor, Paper, Text, Title } from '@mantine/core'
import { Fragment, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FeedFailed, PageOff, StaleNote } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'
import { readBoot } from '@/nav/boot'
import { isScreen, usePublicFeed } from '@/lib/publicFeed'
import { clock, dateOnly, dayClock } from '@/lib/time'

type Kind = 'talk' | 'tournament' | 'meal' | 'quiet' | 'other'
type Item = { id: string; title: string; kind: Kind; start: number; end: number | null; where?: string; note?: string }
export type Agenda = {
  event: { start: number | null; end: number | null }
  phase: 'unknown' | 'before' | 'during' | 'after'
  countdown: number | null
  now: Item[]; next: Item[]; quiet: Item | null; items: Item[]
  server_time: number
}

const ends = (i: Item) => i.end ?? i.start + 1800   // no end: half an hour, as floorbit/schedule.py

function when(at: number) {
  return new Date(at * 1000).toDateString() === new Date().toDateString() ? clock(at) : dayClock(at)
}

/** Seconds left to ``target``, ticking every second on the server's clock: a screen whose own
 *  clock is wrong still counts down right. */
function useCountdown(target: number | null, serverNow: number) {
  const [skew] = useState(() => serverNow * 1000 - Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (target == null) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [target])
  if (target == null) return null
  let left = Math.max(0, Math.floor((target * 1000 - (now + skew)) / 1000))
  const d = Math.floor(left / 86400); left -= d * 86400
  const h = Math.floor(left / 3600); left -= h * 3600
  const m = Math.floor(left / 60)
  return { d, h, m, s: left - m * 60 }
}

function Countdown({ target, serverNow }: { target: number; serverNow: number }) {
  const { t } = useTranslation()
  const left = useCountdown(target, serverNow)
  if (!left) return null
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    <div className="fb-agenda-countdown" id="countdown">
      <div><b>{left.d}</b><span>{t('publicAgenda.days')}</span></div>
      <div><b>{pad(left.h)}</b><span>h</span></div>
      <div><b>{pad(left.m)}</b><span>min</span></div>
      <div><b>{pad(left.s)}</b><span>s</span></div>
    </div>
  )
}

function ItemLine({ item, extra }: { item: Item; extra?: string[] }) {
  const { t } = useTranslation()
  const facts = [item.kind !== 'other' ? t(`publicAgenda.kind.${item.kind}`) : '', item.where ?? '', ...(extra ?? [])].filter(Boolean)
  return (
    <div className={`fb-agenda-item fb-agenda-k-${item.kind}`}>
      <b>{item.title}</b>
      {facts.length > 0 && <Text span c="dimmed" size="sm">{facts.join(' · ')}</Text>}
    </div>
  )
}

/** The public schedule (issue #106, docs/schedule.md): countdown, what's on now and next, the
 *  programme by day. For phones and, with ``?screen=1``, a big screen. No account. */
export default function PublicAgenda() {
  const { t, i18n } = useTranslation()
  const screen = isScreen()
  const feed = usePublicFeed<Agenda>('/agenda.json', 60)
  const title = t('publicAgenda.title')
  const event = readBoot().brand.name
  useEffect(() => { if (screen) document.title = `${title} · Floorbit` }, [screen, title])
  const s = feed.data
  let body
  if (feed.off) body = <PageOff title={title} text={t('publicAgenda.off')} />
  else if (feed.failed) body = <FeedFailed title={title} onRetry={feed.retry} />
  else if (!s) body = <Paper withBorder radius="lg" p="lg" mih={160} aria-busy="true" />
  else {
    const now = s.server_time
    // A big screen shows what's still to come; past items (and days with only those) take room.
    const shown = screen ? s.items.filter((i) => ends(i) > now) : s.items
    body = (
      <>
        <header className="fb-agenda-wide">
          <Title order={1} className="fb-wall-title">{event || title}</Title>
          {event && <Text c="dimmed">{title}</Text>}
        </header>
        {s.phase === 'before' && s.event.start != null && (
          <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-wide" aria-live="polite">
            <Title order={2} className="fb-wall-label">{t('publicAgenda.startsIn')}</Title>
            <Countdown target={s.event.start} serverNow={now} />
            <Text c="dimmed" size="sm">{when(s.event.start)}</Text>
          </Paper>
        )}
        {s.phase === 'after' && (
          <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-wide"><Text fw={700}>{t('publicAgenda.over')}</Text></Paper>
        )}
        {s.quiet && (
          <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-quiet fb-agenda-wide" role="status">
            <Text fw={700}>{t('publicAgenda.quiet', { time: when(s.quiet.end ?? s.quiet.start + 1800) })}</Text>
          </Paper>
        )}
        {s.phase !== 'after' && (
          <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-big" id="agenda-now">
            <Title order={2} className="fb-wall-label">{t('publicAgenda.now')}</Title>
            {s.now.filter((i) => i.kind !== 'quiet').length
              ? s.now.filter((i) => i.kind !== 'quiet').map((i) => (
                <ItemLine key={i.id} item={i} extra={i.end ? [t('publicAgenda.until', { time: when(i.end) })] : []} />))
              : <Text c="dimmed" size="sm">{t('publicAgenda.nothingNow')}</Text>}
          </Paper>
        )}
        {s.phase !== 'after' && s.next.length > 0 && (
          <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-big" id="agenda-next">
            <Title order={2} className="fb-wall-label">{t('publicAgenda.next', { time: when(s.next[0].start) })}</Title>
            {s.next.map((i) => <ItemLine key={i.id} item={i} />)}
          </Paper>
        )}
        {!(screen && s.items.length && !shown.length) && <Paper withBorder radius="lg" className="fb-agenda-card fb-agenda-wide fb-agenda-programme">
          <Title order={2} className="fb-wall-label">{t('publicAgenda.programme')}</Title>
          {shown.length ? (
            <ol id="programme">
              {shown.map((i, n) => {
                // A heading before the first item of each day, in the reader's time zone.
                const d = new Date(i.start * 1000).toDateString()
                const heading = n === 0 || d !== new Date(shown[n - 1].start * 1000).toDateString()
                const on = i.start <= now && now < ends(i)
                const past = ends(i) <= now
                return (
                  <Fragment key={i.id}>
                    {heading && <li className="fb-agenda-day">{dateOnly(i.start, i18n.language, { weekday: 'long', day: 'numeric', month: 'long' })}</li>}
                    <li className={on ? 'fb-agenda-on' : past ? 'fb-agenda-past' : undefined}>
                      <span className="fb-agenda-when">{clock(i.start)}</span>
                      <ItemLine item={i} extra={i.note ? [i.note] : []} />
                    </li>
                  </Fragment>
                )
              })}
            </ol>
          ) : <Text c="dimmed" size="sm">{t('publicAgenda.empty')}</Text>}
        </Paper>}
        <Text size="sm" c="dimmed" className="fb-agenda-wide fb-wall-note">
          {t('publicAgenda.updated', { time: clock(now) })}
          {!screen && s.items.length > 0 && <> · <Anchor href="/agenda.ics" c="dimmed" size="sm" underline="always">{t('publicAgenda.subscribe')}</Anchor></>}
        </Text>
      </>
    )
  }
  const stale = feed.stale && <StaleNote since={feed.lastGood} />
  if (screen) return <main className="fb-agenda fb-agenda--screen">{stale}{body}</main>
  return <PublicPage title={title} size="page">{stale}<div className="fb-agenda">{body}</div></PublicPage>
}
