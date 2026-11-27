import { Anchor, Group, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EndpointAnswer } from '@/api/types'
import { Card, EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { EndpointTable } from '@/pages/endpoints/EndpointTable'

/** The device's MAC and IP tab (issue #903): every machine seen on its ports, newest first, from
 *  the IP and MAC history. Names MACs and IPs, so it needs seats.view like that page. */
export function DeviceEndpoints({ name }: { name: string }) {
  const { t } = useTranslation()
  const ask = `device=${encodeURIComponent(name)}`
  const q = useQuery({ queryKey: qk.endpoints(ask), queryFn: () => get<EndpointAnswer>(`/api/endpoints?${ask}`), refetchInterval: 60_000 })
  const rows = q.data?.rows ?? []
  if (q.isPending) return <LoadingState rows={3} />
  return (
    <>
      <ErrorBanner error={q.error ?? q.data?.status.error ?? null} onRetry={() => void q.refetch()} />
      {!rows.length ? (
        <EmptyState title={t('deviceNetworks.noMacs')} description={t('endpoints.noneDesc', { days: q.data?.status.keep_days ?? 7 })} />
      ) : (
        <>
          <Group justify="space-between" mb="xs">
            <Text size="sm" c="dimmed">{t('deviceNetworks.macsHint')}</Text>
            <Anchor component={Link} to="/endpoints" size="sm">{t('deviceNetworks.allHistory')}</Anchor>
          </Group>
          <Card heading={2} padded={false}><EndpointTable rows={rows} now={q.dataUpdatedAt / 1000} label={t('deviceNetworks.macsLabel', { name })} /></Card>
        </>
      )}
    </>
  )
}
