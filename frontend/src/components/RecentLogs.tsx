import { Button, Text } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { LogsData } from '@/api/types'
import { Card, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { LogTable } from '@/pages/Logs'

const LINES = 20

/** The newest syslog lines of a seat, or of a switch when there is no seat: on a problem's page
 *  (issue #882) and an incident's (issue #913), so the first look needs no trip to the Logs page.
 *  Lines name MACs and IPs: the pages show it only to those who may see people. */
export function RecentLogs({ seat, device }: { seat?: string | null; device?: string | null }) {
  const { t } = useTranslation()
  const filter = seat ? `seat=${encodeURIComponent(seat)}` : `device=${encodeURIComponent(device ?? '')}`
  const logs = useQuery({
    queryKey: qk.logs(`recent:${filter}`),
    queryFn: () => get<LogsData>(`/api/logs?${filter}&limit=${LINES}`),
    refetchInterval: 15_000,
  })
  const lines = logs.data?.lines ?? []
  return (
    <Card heading={2} title={t('recentLogs.title')}
      actions={<Button size="xs" variant="default" component={Link} to={`/logs?${filter}`} rightSection={<IconExternalLink size={14} />}>
        {t('recentLogs.open')}</Button>}>
      <ErrorBanner error={logs.error} />
      {logs.isPending ? <LoadingState rows={3} /> : lines.length === 0 ? (
        <Text size="sm" c="dimmed">{t(seat ? 'recentLogs.noneSeat' : 'recentLogs.none', { name: seat ?? device })}</Text>
      ) : (
        <LogTable lines={lines} store={false} source="syslog" />
      )}
    </Card>
  )
}
