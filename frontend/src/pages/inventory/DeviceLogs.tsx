import { Button, Group, Select, Text, TextInput } from '@mantine/core'
import { IconExternalLink, IconFileText, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { LogsData } from '@/api/types'
import { EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { LogTable } from '@/pages/Logs'

const SEVERITIES = ['emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug'] as const

/** One device's syslog (issue #903): the Logs page narrowed to it, newest first, following along. */
export function DeviceLogs({ name }: { name: string }) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const [settled, setSettled] = useState('')
  const [severity, setSeverity] = useState<string | null>(null)
  useEffect(() => {
    const id = setTimeout(() => setSettled(q), 300)
    return () => clearTimeout(id)
  }, [q])
  const query = new URLSearchParams({ device: name, limit: '200', ...(settled ? { q: settled } : {}), ...(severity ? { severity } : {}) })
  const logs = useQuery({
    queryKey: qk.logs(`device:${query.toString()}`),
    queryFn: () => get<LogsData>(`/api/logs?${query.toString()}`),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })
  const lines = logs.data?.lines ?? []
  const narrowed = !!settled || !!severity
  return (
    <>
      <Group justify="space-between" wrap="wrap" mb="sm" gap="sm">
        <Group gap="sm" wrap="wrap">
          <TextInput size="xs" w={220} leftSection={<IconSearch size={14} />} placeholder={t('deviceTabs.logs.search')}
            aria-label={t('deviceTabs.logs.search')} value={q} onChange={(e) => setQ(e.currentTarget.value)} />
          <Select size="xs" w={150} clearable placeholder={t('deviceTabs.logs.anyLevel')} aria-label={t('deviceTabs.logs.level')}
            value={severity} onChange={setSeverity} data={SEVERITIES.map((s) => ({ value: s, label: t(`logs.sev.${s}`) }))} />
        </Group>
        <Button size="xs" variant="default" component={Link} to={`/logs?device=${encodeURIComponent(name)}`}
          rightSection={<IconExternalLink size={14} />}>{t('deviceTabs.logs.open')}</Button>
      </Group>
      <ErrorBanner error={logs.error} />
      {logs.isPending ? <LoadingState rows={4} /> : lines.length === 0 ? (
        <EmptyState icon={<IconFileText size={24} />} title={t(narrowed ? 'deviceTabs.logs.noMatch' : 'deviceTabs.logs.none')}
          description={narrowed ? undefined : t('deviceTabs.logs.noneHelp', { name })} />
      ) : (
        <>
          <LogTable lines={lines} store={false} source="syslog" />
          {lines.length >= 200 && <Text size="xs" c="dimmed" mt="xs">{t('deviceTabs.logs.more')}</Text>}
        </>
      )}
    </>
  )
}
