import { Anchor, Badge, Group, Loader, Stack, Text } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { StatusPageData } from '@/api/types'
import { ErrorBanner } from '@/components/ui'
import { clock } from '@/lib/time'
import type { ViewProps } from '@/widgets/views'
import { AreaLine } from '../NetworkStatus'
import { COLOR } from './state'

/** What the public status page says now and which areas are down. Posting updates and setting the
 *  state by hand stay on the Network status page. */
export default function NetworkStatusView({ expanded }: ViewProps) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.statusPage, queryFn: () => get<StatusPageData>('/api/status-page'), refetchInterval: 30_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.statusPage })
  useLiveEvent('status_page.changed', refresh)
  useLiveEvent('switch.status', refresh)
  const d = query.data
  if (query.isPending || !d) return <><ErrorBanner error={query.error} /><Loader size="sm" aria-label={t('common.loading')} /></>
  return (
    <Stack gap="sm">
      <ErrorBanner error={query.error} />
      <Group gap="sm">
        <Badge size="lg" color={COLOR[d.state]} variant="filled" tt="none">{t(`status.state.${d.state}`)}</Badge>
        {d.since && <Text size="sm" c="dimmed">{t('status.since', { time: clock(d.since, i18n.language) })}</Text>}
      </Group>
      {d.crew_areas.length === 0 ? <Text size="sm" c="dimmed">{t('status.noAreas')}</Text> : (
        <Stack gap="xs">{d.crew_areas.slice(0, expanded ? undefined : 4).map((a) => <AreaLine key={`${a.hall}-${a.block}`} a={a} />)}</Stack>
      )}
      {expanded && d.updates.length > 0 && (
        <Stack gap={4}>
          {d.updates.slice(0, 5).map((u) => (
            <Text key={u.id} size="sm"><Text span c="dimmed">{clock(u.at, i18n.language)}</Text> {u.text}</Text>
          ))}
        </Stack>
      )}
      <Anchor href="/network-status" size="sm">{t('status.manage')}</Anchor>
    </Stack>
  )
}
