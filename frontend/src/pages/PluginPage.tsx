import { Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PluginPageData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { TileGrid } from '@/widgets/PluginTiles'

/** A plugin's own page (plugin.yaml ``pages:``), in the sidebar's Plugins section: its widgets and
 *  actions, drawn like dashboard tiles. Floorbit draws it; the plugin only says what goes on it. */
export default function PluginPage() {
  const { t } = useTranslation()
  const { plugin = '', page = '' } = useParams()
  const url = `/api/plugins/${encodeURIComponent(plugin)}/pages/${encodeURIComponent(page)}`
  const q = useQuery({ queryKey: qk.pluginPage(url), queryFn: () => get<PluginPageData>(url) })
  const title = q.data?.label ?? t('plugins.pageTitle')
  return (
    <Layout title={title}>
      <PageHead title={title} desc={q.data && q.data.plugin_name !== q.data.label ? t('plugins.pageFrom', { plugin: q.data.plugin_name }) : undefined} />
      {q.isPending && <LoadingState rows={3} />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {q.data && !q.data.tiles.length && <Text c="dimmed">{t('plugins.pageEmpty')}</Text>}
      {q.data && q.data.tiles.length > 0 && <TileGrid tiles={q.data.tiles} columns={q.data.columns} />}
    </Layout>
  )
}
