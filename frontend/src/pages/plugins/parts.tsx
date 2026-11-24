import { Badge, Switch, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { usePluginLog } from '@/api/queries'
import type { PluginInfo } from '@/api/types'
import { LoadingState } from '@bitsandbricks/ui'
import { pluginName } from '@/lib/pluginName'
import type { useToggle } from './toggle'

/** Where the plugin's own documents stand against the ``schema:`` this version knows. */
export function DataSchema({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const want = plugin.schema ?? 0
  const have = plugin.data_schema ?? 0
  if (have === want) return <Text size="sm" c="dimmed">{t('plugins.schemaOk', { n: want })}</Text>
  if (have > want) return <Text size="sm" className="fb-tone-err">{t('plugins.schemaNewer', { have, want })}</Text>
  return <Text size="sm" className="fb-tone-warn">{t('plugins.schemaBehind', { have, want })}</Text>
}

export function PluginLog({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data, error, isPending } = usePluginLog(id, true)
  if (isPending) return <LoadingState rows={3} />
  if (error) return <Text className="fb-tone-err">✕ {error.message}</Text>
  return <pre className="fb-log">{data.lines.length ? data.lines.map((l) => `${l.time}  ${l.line}`).join('\n') : t('plugins.emptyLog')}</pre>
}

export function OnOff({ plugin, toggle, ml = 'auto' }: { plugin: PluginInfo; toggle: ReturnType<typeof useToggle>; ml?: string | number }) {
  const { t } = useTranslation()
  return (
    <Switch
      ml={ml}
      checked={plugin.enabled}
      disabled={!!plugin.error || toggle.isPending}
      onChange={(e) => toggle.mutate(e.currentTarget.checked)}
      label={plugin.enabled ? t('plugins.on') : t('plugins.off')}
      aria-label={`${pluginName(t, plugin.id, plugin.name)}: ${plugin.enabled ? t('plugins.on') : t('plugins.off')}`}
    />
  )
}

export function Badges({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const trust = ['builtin', 'development', 'official'].includes(plugin.trust) ? t(`plugins.trust.${plugin.trust}`) : plugin.trust
  return (
    <>
      {plugin.version && <Text size="sm" c="dimmed" ff="monospace">v{plugin.version}</Text>}
      <Badge variant="light" color={plugin.trust === 'builtin' || plugin.trust === 'official' ? 'bit' : 'warn'}>{trust}</Badge>
      {plugin.uses.some((u) => u.id === 'agent') && <Badge variant="outline" color="gray">{t('plugins.agent')}</Badge>}
    </>
  )
}
