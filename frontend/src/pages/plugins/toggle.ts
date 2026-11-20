import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { put } from '@/api/client'
import { qk } from '@/api/keys'
import type { PluginInfo } from '@/api/types'
import { pluginName } from '@/lib/pluginName'

/** Turns a plugin on or off; ``done`` gets the sentence to show. */
export function useToggle(plugin: PluginInfo, done: (ok: boolean, text: string) => void) {
  const { t } = useTranslation()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => put<{ plugins: PluginInfo[] }>(`/api/settings/plugins/${encodeURIComponent(plugin.id)}`, { enabled }),
    onSuccess: (data, enabled) => {
      client.setQueryData(qk.plugins, { plugins: data.plugins })
      void client.invalidateQueries({ queryKey: qk.dashboard })
      done(true, t(enabled ? 'plugins.turnedOn' : 'plugins.turnedOff', { name: pluginName(t, plugin.id, plugin.name) }))
    },
    onError: (e) => done(false, e.message),
  })
}

/** What the plugin does, in the reader's language for the built-in ones. */
export function describe(plugin: PluginInfo, t: ReturnType<typeof useTranslation>['t']) {
  return plugin.trust === 'builtin'
    ? t([`integrationSettings.plugins.${plugin.id}`, `integrationSettings.sections.plugin-${plugin.id}.desc`], { defaultValue: plugin.description })
    : plugin.description
}
