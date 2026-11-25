import { Badge, Switch, Text, Tooltip } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { usePluginLog } from '@/api/queries'
import type { PluginActivityState, PluginInfo } from '@/api/types'
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

export function OnOff({ plugin, toggle, ml = 'auto', bare = false }: {
  plugin: PluginInfo; toggle: ReturnType<typeof useToggle>; ml?: string | number; bare?: boolean
}) {
  const { t } = useTranslation()
  return (
    <Switch
      ml={ml}
      checked={plugin.enabled}
      disabled={!!plugin.error || toggle.isPending}
      onChange={(e) => toggle.mutate(e.currentTarget.checked)}
      label={bare ? undefined : plugin.enabled ? t('plugins.on') : t('plugins.off')}
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

const TONE: Record<PluginActivityState, string> = {
  broken: 'down', failing: 'down', off: 'gray', no_agent: 'warn', not_configured: 'warn',
  receiving: 'up', waiting: 'gray', on: 'up',
}

/** What the plugin does (#1435), top right on its card; the sentence behind it on hover. */
export function StateBadge({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const activity = plugin.activity ?? { state: plugin.error ? 'broken' : plugin.enabled ? 'on' : 'off', values: {} }
  return (
    <Tooltip label={t(`plugins.activity.${activity.state}.text`, activity.values)} withArrow multiline maw={280}>
      <Badge variant="light" color={TONE[activity.state]} tt="none" data-state={activity.state} style={{ flex: 'none' }}>
        {t(`plugins.activity.${activity.state}.label`)}
      </Badge>
    </Tooltip>
  )
}

/** Version, where it comes from and where it runs, in one quiet line at the card's foot. */
export function Meta({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const trust = ['builtin', 'development', 'official'].includes(plugin.trust) ? t(`plugins.trust.${plugin.trust}`) : plugin.trust
  const parts = [plugin.version && `v${plugin.version}`, trust, plugin.uses.some((u) => u.id === 'agent') && t('plugins.meta.agent')]
  return <Text size="xs" c="dimmed" truncate>{parts.filter(Boolean).join(' · ')}</Text>
}
