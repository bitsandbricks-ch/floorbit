import { Anchor, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Services as ServicesData } from '@/api/types'
import { ErrorBanner } from '@/components/ui'
import type { ViewProps } from '@/widgets/views'
import { LanCacheCard, ResolverCard, SiteCard, UplinkCard } from '../Services'

/** The internet lines, DNS resolvers, the sites players need and the LAN cache: up, how full, how
 *  fast. Small, only what isn't up; opened up, every card. They are set up on the Services page. */
export default function ServicesView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.services, queryFn: () => get<ServicesData>('/api/services'), refetchInterval: 15_000 })
  const d = q.data
  if (q.isPending || !d) return <><ErrorBanner error={q.error} /><Loader size="sm" aria-label={t('common.loading')} /></>
  const keep = <T extends { status: string }>(xs: T[]) => (expanded ? xs : xs.filter((x) => x.status !== 'up'))
  const uplinks = keep(d.uplinks), resolvers = keep(d.resolvers), sites = keep(d.sites ?? [])
  const nothing = !d.uplinks.length && !d.resolvers.length && !(d.sites ?? []).length && !d.lan_cache
  const quiet = !uplinks.length && !resolvers.length && !sites.length
  const cols = expanded ? { base: 1, sm: 2, lg: 3 } : { base: 1, sm: 2 }
  return (
    <Stack gap="md">
      <ErrorBanner error={q.error} />
      {nothing ? <Text c="dimmed">{t('services.nothing')}</Text> : (
        <>
          {!expanded && quiet && <Text c="dimmed">{t('services.allUp')}</Text>}
          {[
            { id: 'uplinks', items: uplinks.map((u) => <UplinkCard key={u.id} uplink={u} />) },
            { id: 'resolvers', items: resolvers.map((r) => <ResolverCard key={r.id} resolver={r} />) },
            { id: 'sites', items: sites.map((s) => <SiteCard key={s.id} site={s} />) },
          ].filter((g) => g.items.length).map((g) => (
            <Stack key={g.id} gap="xs">
              {expanded && <Title order={3} size="h5">{t(`services.${g.id}`)}</Title>}
              <SimpleGrid cols={cols} spacing="md">{g.items}</SimpleGrid>
            </Stack>
          ))}
          {expanded && d.lan_cache && (
            <Stack gap="xs">
              <Title order={3} size="h5">{t('services.lanCache')}</Title>
              <SimpleGrid cols={cols} spacing="md"><LanCacheCard cache={d.lan_cache} /></SimpleGrid>
            </Stack>
          )}
        </>
      )}
      <Anchor href="/services" size="sm">{t('services.manage')}</Anchor>
    </Stack>
  )
}
