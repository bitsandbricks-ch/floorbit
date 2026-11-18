import { Anchor, Chip, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import type { PlanDrawing } from '@/api/types'
import { HallSketch } from '@/components/HallSketch'
import { FeedFailed, PageOff, StaleNote } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'
import { usePublicFeed } from '@/lib/publicFeed'
import { clock } from '@/lib/time'

export type PublicHallData = {
  hall: string; halls: { id: string; name: string }[]; drawing: PlanDrawing | null
  online: number | null; total: number; updated: number | null; finder: boolean; agenda: boolean
}

/** The public attendee view (issue #19, docs/kiosk.md): the hall with every seat online or not, for
 *  phones and the event website. Seat numbers and online or not, nothing else. */
export default function PublicHall() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const hall = params.get('hall')
  const feed = usePublicFeed<PublicHallData>(`/api/public/hall${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`, 60)
  const title = t('publicHall.title')
  const h = feed.data
  let body
  if (feed.off) body = <PageOff title={title} text={t('publicHall.off')} />
  else if (feed.failed) body = <FeedFailed title={title} onRetry={feed.retry} />
  else if (!h) body = <Paper withBorder radius="lg" p="lg" mih={240} aria-busy="true" />
  else {
    body = (
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm">
          <Title order={1} size="h3">{title}</Title>
          {h.halls.length > 0 && (
            <Chip.Group value={h.hall} onChange={(id) => setParams({ hall: id as string }, { replace: true })}>
              <Group gap={6} role="radiogroup" aria-label={t('publicHall.halls')}>
                {h.halls.map((x) => <Chip key={x.id} value={x.id} size="sm">{x.name}</Chip>)}
              </Group>
            </Chip.Group>
          )}
          {!h.drawing ? <Text c="dimmed">{t('publicHall.empty')}</Text> : (
            <>
              <Text c="dimmed">
                {t('publicHall.intro')}
                {h.finder && <> <Anchor href="/find">{t('publicHall.find')}</Anchor></>}
                {h.agenda && <> · <Anchor href="/agenda">{t('publicHall.agenda')}</Anchor></>}
              </Text>
              <Group justify="space-between" align="baseline" gap="xs">
                <Text fz={20} fw={600} aria-live="polite" id="hall-count">
                  {h.online != null ? t('publicHall.count', { online: h.online, total: h.total }) : ''}
                </Text>
                <div className="fb-hall-legend">
                  <span style={{ ['--k' as string]: 'var(--color-up)' }}>{t('publicHall.online')}</span>
                  <span style={{ ['--k' as string]: 'var(--color-surface)' }}>{t('publicHall.offline')}</span>
                </div>
              </Group>
              {h.online == null && <Text c="warn" role="status">{t('publicHall.unknown')}</Text>}
              <HallSketch drawing={h.drawing} label={t('publicHall.map')} cellClass={(c) => (c.on ? 'on' : '')} />
              {h.updated && <Text size="sm" c="dimmed">{t('publicHall.updated', { time: clock(h.updated) })}</Text>}
            </>
          )}
        </Stack>
      </Paper>
    )
  }
  return (
    <PublicPage title={title} size="board">
      {feed.stale && <StaleNote since={feed.lastGood} />}
      {body}
    </PublicPage>
  )
}
