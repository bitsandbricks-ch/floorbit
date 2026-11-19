import { Alert, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { usePlugins } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { LoadingState } from '@/components/ui'
import { PluginCard } from './Plugins'
import { LibreNMSAlertsSetup } from './plugins/LibreNMSAlertsSetup'
import { SectionPanel, SettingsForm } from './settings/editor'
import { useSettingsEditor } from './settings/model'
import { pluginName } from '@/lib/pluginName'

/** One plugin's page: on/off, test, actions and log, and its settings (moved here from the
 *  Settings page so that one doesn't grow with every plugin). */
export default function PluginSettings() {
  const { t } = useTranslation()
  const { id } = useParams()
  const plugins = usePlugins()
  const ed = useSettingsEditor()
  const plugin = plugins.data?.plugins.find((p) => p.id === id)
  const section = plugin?.settings_section ? ed.d?.sections.find((s) => s.id === plugin.settings_section) : undefined
  const error = plugins.error ?? ed.query.error

  return (
    <Layout title={plugin ? pluginName(t, plugin.id, plugin.name) : t('plugins.title')} back={{ href: '/settings/plugins', label: t('plugins.title') }}>
      <PageHead title={plugin ? pluginName(t, plugin.id, plugin.name) : t('plugins.title')} />
      {(plugins.isPending || ed.query.isPending) && <LoadingState rows={3} />}
      {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
      {plugins.data && !plugin && <Text>{t('plugins.notFound', { id })}</Text>}
      {plugin && ed.d && (
        <Stack gap="md">
          <PluginCard plugin={plugin} titled={false} />
          {/* The one plugin with something to paste elsewhere: its token stays behind a button. */}
          {plugin.id === 'librenms-alerts' && plugin.enabled && <LibreNMSAlertsSetup />}
          {section && (
            <SettingsForm ed={ed}>
              <SectionPanel ed={ed} section={section} title={t('plugins.settings')} />
            </SettingsForm>
          )}
        </Stack>
      )}
    </Layout>
  )
}
