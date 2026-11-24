import { Anchor, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { GameServerList, Services as ServicesData } from '@/api/types'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { ServiceGroup } from '@/widgets/ServiceList'
import { TYPES, serviceRows } from '@/widgets/serviceRows'
import type { ViewProps } from '@/widgets/views'

/** The Services page's list on a dashboard (issue #889): the same rows. Small, only what isn't up;
 *  opened up, every service by type. They are set up on the Services page. */
export default function ServicesView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.services, queryFn: () => get<ServicesData>('/api/services'), refetchInterval: 15_000 })
  const games = useQuery({ queryKey: qk.gameServers, queryFn: () => get<GameServerList>('/api/game-servers'), refetchInterval: 15_000 })
  if (!q.data || !games.data) return <><ErrorBanner error={q.error ?? games.error} onRetry={() => { void q.refetch(); void games.refetch() }} /><LoadingState lines /></>
  const rows = serviceRows(t, q.data, games.data, {})
  const shown = expanded ? rows : rows.filter((r) => r.status !== 'up')
  return (
    <Stack gap="md">
      <ErrorBanner error={q.error ?? games.error} />
      {!rows.length ? <Text c="dimmed">{t('services.nothing')}</Text> : !shown.length ? <Text c="dimmed">{t('services.allUp')}</Text>
        : expanded ? TYPES.map((k) => ({ k, rows: shown.filter((r) => r.type === k) })).filter((g) => g.rows.length).map((g) => (
          <ServiceGroup key={g.k} title={t(`services.groups.${g.k}`)} rows={g.rows} />
        )) : <ServiceGroup rows={shown} showType />}
      <Anchor href="/services" size="sm">{t('services.manage')}</Anchor>
    </Stack>
  )
}
