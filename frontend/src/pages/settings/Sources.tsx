import { SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { usePlugins } from '@/api/queries'
import type { PluginInfo } from '@/api/types'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { PluginRow } from '../plugins/PluginRow'

/** Settings > Sources (#1587): the plugins that come with Floorbit. The ones it asks (NetBox,
 *  LibreNMS, Loki, ...) first, then what every agent does (telemetry, syslog, the front door, ...),
 *  each with its page for settings and its switch. Marketplace add-ons stay under Plugins. */
export default function Sources() {
  const { t } = useTranslation()
  const { data, error, isPending } = usePlugins()
  const builtin = (data?.plugins ?? []).filter((p) => p.trust === 'builtin')
  const hosted = builtin.filter((p) => !p.agent)
  const agent = builtin.filter((p) => p.agent)
  return (
    <Stack gap="lg">
      {isPending && <LoadingState rows={3} />}
      <ErrorBanner error={error} />
      {data && <Group title={t('sources.hosted.title')} desc={t('sources.hosted.desc')} plugins={hosted} />}
      {data && <Group title={t('sources.agent.title')} desc={t('sources.agent.desc')} plugins={agent} />}
    </Stack>
  )
}

function Group({ title, desc, plugins }: { title: string; desc: string; plugins: PluginInfo[] }) {
  if (!plugins.length) return null
  return (
    <Stack gap="sm" component="section" aria-label={title}>
      <div>
        <Title order={2} fz="lg">{title}</Title>
        <Text size="sm" c="dimmed">{desc}</Text>
      </div>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" component="ul" className="fb-plain-list">
        {plugins.map((p) => <PluginRow key={p.id} plugin={p} />)}
      </SimpleGrid>
    </Stack>
  )
}
