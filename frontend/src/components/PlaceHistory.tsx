import { Button, Text } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { TimelineEntry } from '@/api/types'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { TimelineRow } from '@/pages/Timeline'

/** What happened at a problem's or an incident's place, from the event changelog (issues #882, #913):
 *  outages, incidents and alerts, newest first. The full changelog needs `audit.read`, so the link to
 *  it shows only for those who have it. */
export function PlaceHistory({ entries, loading, error, search, canOpen }: {
  entries: TimelineEntry[] | undefined
  loading?: boolean
  error?: Error | null
  /** What the changelog link searches for: the switch or seat. */
  search?: string | null
  canOpen?: boolean
}) {
  const { t, i18n } = useTranslation()
  return (
    <Panel title={t('placeHistory.title')}
      actions={canOpen && search ? (
        <Button size="xs" variant="default" component={Link} to={`/timeline?q=${encodeURIComponent(search)}`}
          rightSection={<IconExternalLink size={14} />}>{t('placeHistory.open')}</Button>
      ) : undefined}>
      <ErrorBanner error={error ?? null} />
      {loading ? <LoadingState rows={2} /> : !entries?.length ? (
        <Text size="sm" c="dimmed">{t('placeHistory.none')}</Text>
      ) : (
        <div data-testid="place-history">
          {entries.map((e, i) => <TimelineRow key={`${e.t}-${i}`} e={e} lang={i18n.language} />)}
        </div>
      )}
    </Panel>
  )
}
