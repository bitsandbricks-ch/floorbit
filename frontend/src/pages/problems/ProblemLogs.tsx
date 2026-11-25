import { Button, Text } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { LogsData, Problem } from '@/api/types'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { LogTable } from '@/pages/Logs'

const LINES = 20

/** The newest syslog lines of the seat or switch a problem is about (issue #882), so the first look
 *  needs no trip to the Logs page. Lines name MACs and IPs, so only for those who may see people. */
export function ProblemLogs({ p }: { p: Problem }) {
  const { t } = useTranslation()
  const filter = p.seat ? `seat=${encodeURIComponent(p.seat)}` : `device=${encodeURIComponent(p.device ?? '')}`
  const logs = useQuery({
    queryKey: qk.logs(`problem:${filter}`),
    queryFn: () => get<LogsData>(`/api/logs?${filter}&limit=${LINES}`),
    refetchInterval: 15_000,
  })
  const lines = logs.data?.lines ?? []
  return (
    <Panel title={t('problemLogs.title')}
      actions={<Button size="xs" variant="default" component={Link} to={`/logs?${filter}`} rightSection={<IconExternalLink size={14} />}>
        {t('problemLogs.open')}</Button>}>
      <ErrorBanner error={logs.error} />
      {logs.isPending ? <LoadingState rows={3} /> : lines.length === 0 ? (
        <Text size="sm" c="dimmed">{t(p.seat ? 'problemLogs.noneSeat' : 'problemLogs.none', { name: p.seat ?? p.device })}</Text>
      ) : (
        <LogTable lines={lines} store={false} source="syslog" />
      )}
    </Panel>
  )
}
