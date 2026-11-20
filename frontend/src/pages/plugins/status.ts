import type { Agent, PluginInfo } from '@/api/types'

export type PluginTone = 'up' | 'warn' | 'down' | 'off'
/** One line on whether a plugin works, as a text key and its values (plugins.state.*). */
export interface PluginState { tone: PluginTone; key: string; values?: Record<string, string | number> }

const names = (list: Agent[]) => list.map((a) => a.name).join(', ')

/** Whether a plugin works (#995): it loaded, it is on, and, for one with an agent part, how that
 *  part does on the local agents (their last report). ``agents`` is undefined while they load. */
export function pluginState(plugin: PluginInfo, agents?: Agent[]): PluginState {
  if (plugin.error) return { tone: 'down', key: 'broken', values: { error: plugin.error } }
  if (!plugin.enabled) return { tone: 'off', key: 'off' }
  if (!plugin.uses.some((u) => u.id === 'agent') || !agents) return { tone: 'up', key: 'working' }
  if (!agents.length) return { tone: 'warn', key: 'noAgent' }
  const health = (a: Agent) => a.report?.plugins?.[plugin.id]
  const failing = agents.filter((a) => health(a)?.status === 'error')
  if (failing.length) return { tone: 'down', key: 'failing', values: { names: names(failing) } }
  const running = agents.filter((a) => health(a)?.running)
  if (!running.length) return { tone: 'warn', key: 'notRunning' }
  const warning = running.filter((a) => health(a)?.status === 'warning')
  if (warning.length) return { tone: 'warn', key: 'warning', values: { names: names(warning) } }
  return { tone: 'up', key: 'workingOn', values: { count: running.length, total: agents.length } }
}
