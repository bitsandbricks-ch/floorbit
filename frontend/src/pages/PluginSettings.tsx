import { Alert, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { usePlugins } from '@/api/queries'
import type { Agent, PluginInfo } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { PageTabs } from '@/components/PageTabs'
import { usePageTab } from '@/components/pageTab'
import { LoadingState } from '@/components/ui'
import { pluginName } from '@/lib/pluginName'
import { PluginIcon } from './plugins/icon'
import { OnOff, PluginLog } from './plugins/parts'
import { PerAgent, PluginOverview } from './plugins/PluginOverview'
import { describe, useToggle } from './plugins/toggle'
import { SectionPanel, SettingsForm } from './settings/editor'
import { useSettingsEditor } from './settings/model'

/** One plugin's page (#995): its name, what it does once, on/off, and a line on whether it works;
 *  then tabs for its settings, how its agent part does on each local agent, and its log. */
export default function PluginSettings() {
  const { t } = useTranslation()
  const { id } = useParams()
  const plugins = usePlugins()
  const ed = useSettingsEditor()
  const plugin = plugins.data?.plugins.find((p) => p.id === id)
  const section = plugin?.settings_section ? ed.d?.sections.find((s) => s.id === plugin.settings_section) : undefined
  const onAgent = !!plugin?.uses.some((u) => u.id === 'agent')
  // Only a plugin with an agent part asks for the agents (their last report says how it does there).
  const agents = useQuery({ queryKey: qk.agents, queryFn: () => get<{ agents: Agent[] }>('/api/agents'), enabled: onAgent, refetchInterval: 10_000 })
  const tabs = [
    ...(section ? [{ id: 'settings', label: t('plugins.settings') }] : []),
    ...(onAgent ? [{ id: 'agents', label: t('plugins.perAgent.title'), count: agents.data?.agents.length ?? null }] : []),
    { id: 'log', label: t('plugins.log') },
  ]
  const [tab, setTab] = usePageTab(tabs.map((x) => x.id))
  const name = plugin ? pluginName(t, plugin.id, plugin.name) : t('plugins.title')
  const error = plugins.error ?? ed.query.error

  return (
    <Layout title={name} back={{ href: '/settings/plugins', label: t('plugins.title') }}>
      <PageHead title={name} icon={plugin ? <PluginIcon name={plugin.icon} size={28} /> : undefined}
        kicker={plugin?.description ? describe(plugin, t) : undefined}
        actions={plugin ? <PluginSwitch plugin={plugin} /> : undefined} />
      {(plugins.isPending || ed.query.isPending) && <LoadingState rows={3} />}
      {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
      {plugins.data && !plugin && <Text>{t('plugins.notFound', { id })}</Text>}
      {plugin && ed.d && (
        <>
          <PluginOverview plugin={plugin} agents={onAgent ? agents.data?.agents : undefined} />
          <PageTabs label={name} value={tab} onChange={setTab} tabs={tabs} />
          <div role="tabpanel" aria-labelledby={`fb-tab-${tab}`}>
            {tab === 'settings' && section && (
              <SettingsForm ed={ed}>
                <SectionPanel ed={ed} section={section} title={t('plugins.settings')} desc={null} />
              </SettingsForm>
            )}
            {tab === 'agents' && (agents.data ? <PerAgent plugin={plugin} agents={agents.data.agents} /> : <LoadingState rows={2} />)}
            {tab === 'log' && <PluginLog id={plugin.id} />}
          </div>
        </>
      )}
    </Layout>
  )
}

/** On/off next to the title; the switch shows its state itself, so only a failure says more. */
function PluginSwitch({ plugin }: { plugin: PluginInfo }) {
  const toggle = useToggle(plugin, (ok, text) => { if (!ok) notifications.show({ color: 'down', message: text }) })
  return <OnOff plugin={plugin} toggle={toggle} ml={0} />
}
