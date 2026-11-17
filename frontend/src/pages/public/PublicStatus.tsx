import { Anchor, Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { FeedFailed, PageOff, StaleNote } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'
import { usePublicFeed } from '@/lib/publicFeed'
import { clock, dayClock } from '@/lib/time'

type State = 'operational' | 'degraded' | 'outage' | 'maintenance' | 'unknown'
type Area = { hall?: string; block?: string; rows?: string; seats?: number | null; switches?: string[] }
type Maintenance = { id: string; start: number; end: number; text: string; area?: string }
type Update = { at: number; text: string; state?: State | null; area?: string }
export type PublicStatusData = {
  state: State; since: number | null; checked_at: number
  areas: Area[]; recovered: Area[]; recovered_at: number | null
  planned: Maintenance[]; maintenance_now: Maintenance | null
  updates: Update[]; override?: unknown
}

/** A time today as "14:05", on another day as "Sat 14:05", always 24-hour. */
function when(at: number) {
  return new Date(at * 1000).toDateString() === new Date().toDateString() ? clock(at) : dayClock(at)
}

function AreaList({ areas, state }: { areas: Area[]; state: State }) {
  const { t } = useTranslation()
  return (
    <ul className="fb-status-list">
      {areas.map((a, i) => {
        const name = a.block ? t('publicStatus.block', { name: a.block })
          : a.hall ? t('publicStatus.hallWide', { name: a.hall }) : t('publicStatus.somewhere')
        const facts = [a.rows ? t('publicStatus.rows', { rows: a.rows }) : '',
          a.seats ? t('publicStatus.seats', { count: a.seats }) : '',
          a.switches?.length ? t('publicStatus.switches', { names: a.switches.join(', ') }) : ''].filter(Boolean)
        return (
          <li key={i} className={`fb-status-k-${state}`}>
            <Text fw={600}>{name}{a.block && a.hall ? ` · ${a.hall}` : ''}</Text>
            {facts.length > 0 && <Text size="sm" c="dimmed">{facts.join(' · ')}</Text>}
          </li>
        )
      })}
    </ul>
  )
}

/** The public network status page (issue #101, docs/status-page.md): attendees, no account.
 *  Reads /status.json every minute; the crew's side is /network-status. */
export default function PublicStatus() {
  const { t } = useTranslation()
  const feed = usePublicFeed<PublicStatusData>('/status.json', 60)
  const title = t('publicStatus.title')
  const s = feed.data
  let body
  if (feed.off) body = <PageOff title={title} text={t('publicStatus.off')} />
  else if (feed.failed) body = <FeedFailed title={title} onRetry={feed.retry} />
  else if (!s) body = <Paper withBorder radius="lg" p="lg" mih={120} aria-busy="true" />
  else {
    const now = s.maintenance_now && s.state === 'maintenance' && !s.override ? s.maintenance_now : null
    body = (
      <>
        <Paper withBorder radius="lg" p="lg" className={`fb-status-k-${s.state}`} aria-live="polite">
          <Title order={1} size="sm" c="dimmed" fw={600}>{title}</Title>
          <Group gap="md" mt="sm" wrap="nowrap" align="center">
            <span className="fb-status-dot" aria-hidden="true" />
            <div>
              <Text component="strong" fz={24} fw={700} lh={1.2} data-state={s.state} id="status-state">
                {t(`publicStatus.state.${s.state}`)}
              </Text>
              {now ? (
                <Text id="status-maintenance-now">{now.text} <Text span c="dimmed" size="sm">
                  {t('publicStatus.until', { time: when(now.end) })}{now.area ? ` · ${now.area}` : ''}</Text></Text>
              ) : (
                <Text c="dimmed" size="sm">
                  {t(`publicStatus.detail.${s.state}`)}{s.since ? ` ${t('publicStatus.since', { time: when(s.since) })}` : ''}
                </Text>
              )}
            </div>
          </Group>
        </Paper>
        {s.areas.length > 0 && (
          <Paper withBorder radius="lg" p="lg">
            <Title order={2} size="h4" mb="sm">{t('publicStatus.areas')}</Title>
            <AreaList areas={s.areas} state={s.state} />
          </Paper>
        )}
        {s.planned.length > 0 && (
          <Paper withBorder radius="lg" p="lg" id="status-planned">
            <Title order={2} size="h4" mb="sm">{t('publicStatus.planned')}</Title>
            <ul className="fb-status-list">
              {s.planned.map((m) => (
                <li key={m.id} className="fb-status-k-maintenance">
                  <Text size="sm" c="dimmed">
                    {s.maintenance_now?.id === m.id && <Badge size="sm" color="warn" variant="light" mr={6}>{t('publicStatus.now')}</Badge>}
                    {when(m.start)} – {when(m.end)}{m.area ? ` · ${m.area}` : ''}
                  </Text>
                  <Text>{m.text}</Text>
                </li>
              ))}
            </ul>
          </Paper>
        )}
        {s.recovered.length > 0 && (
          <Paper withBorder radius="lg" p="lg" id="status-recovered">
            <Title order={2} size="h4" mb={4}>{t('publicStatus.recovered')}</Title>
            {s.recovered_at && <Text size="sm" c="dimmed" mb="sm">{t('publicStatus.recoveredAt', { time: when(s.recovered_at) })}</Text>}
            <AreaList areas={s.recovered} state="operational" />
          </Paper>
        )}
        <Paper withBorder radius="lg" p="lg">
          <Title order={2} size="h4" mb="sm">{t('publicStatus.updates')}</Title>
          {s.updates.length ? (
            <ul className="fb-status-list">
              {s.updates.map((u, i) => (
                <li key={`${u.at}-${i}`} className={u.state ? `fb-status-k-${u.state}` : undefined}>
                  <Text size="sm" c="dimmed">{when(u.at)}{u.area ? ` · ${u.area}` : ''}</Text>
                  <Text>{u.text}</Text>
                </li>
              ))}
            </ul>
          ) : <Text c="dimmed">{t('publicStatus.none')}</Text>}
          <Anchor href="/status.atom" size="sm" c="dimmed" underline="always" mt="md" display="inline-block">{t('publicStatus.feed')}</Anchor>
        </Paper>
        <Text size="sm" c="dimmed">{t('publicStatus.updated', { time: when(s.checked_at) })}</Text>
      </>
    )
  }
  return (
    <PublicPage title={title} size="page">
      {feed.stale && <StaleNote since={feed.lastGood} />}
      <Stack gap="md">{body}</Stack>
    </PublicPage>
  )
}
