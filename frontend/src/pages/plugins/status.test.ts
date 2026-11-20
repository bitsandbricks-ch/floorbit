import { describe, expect, it } from 'vitest'
import type { Agent, AgentPluginHealth, PluginInfo } from '@/api/types'
import { pluginState } from './status'

const plugin = { id: 'lancache', name: 'LAN cache', enabled: true, error: null, uses: [{ id: 'agent', label: 'Runs on the agent' }] } as unknown as PluginInfo
const agent = (name: string, h?: Partial<AgentPluginHealth>) =>
  ({ id: name, name, report: h ? { plugins: { lancache: { status: 'ok', running: true, errors: [], metrics: {}, message: '', ...h } } } : {} }) as unknown as Agent

describe('pluginState', () => {
  it('says whether a plugin works, its agent part included', () => {
    expect(pluginState({ ...plugin, error: 'bad yaml' }).key).toBe('broken')
    expect(pluginState({ ...plugin, enabled: false }, []).key).toBe('off')
    expect(pluginState({ ...plugin, uses: [] }, []).key).toBe('working')
    expect(pluginState(plugin, []).key).toBe('noAgent')
    expect(pluginState(plugin, [agent('hall-1')]).key).toBe('notRunning')
    expect(pluginState(plugin, [agent('hall-1', { status: 'warning' })])).toMatchObject({ key: 'warning', values: { names: 'hall-1' } })
    expect(pluginState(plugin, [agent('hall-1'), agent('hall-2', { status: 'error' })])).toMatchObject({ tone: 'down', key: 'failing' })
    expect(pluginState(plugin, [agent('hall-1', {}), agent('hall-2')])).toMatchObject({ tone: 'up', values: { count: 1, total: 2 } })
  })
})
