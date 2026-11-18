import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PluginLayerData, PluginLayerInfo } from '@/api/types'

/** The plugin layer that is on, as ``plugin/layer`` in ``?plugin_layer=``: one at a time, like the heatmap. */
export const PLUGIN_LAYER_PARAM = 'plugin_layer'

export const layerKey = (l: PluginLayerInfo) => `${l.plugin}/${l.id}`

/** The plugins' layers this account may see, and what the chosen one draws (reloaded at its own pace). */
export function usePluginLayer(chosen: string | null) {
  const list = useQuery({
    queryKey: qk.pluginLayers,
    queryFn: () => get<{ layers: PluginLayerInfo[] }>('/api/plugins/layers'),
    staleTime: 60_000,
  })
  const layers = list.data?.layers ?? []
  const info = chosen ? layers.find((l) => layerKey(l) === chosen) : undefined
  const data = useQuery({
    queryKey: qk.pluginLayer(info?.url ?? ''),
    queryFn: () => get<PluginLayerData>(info!.url),
    enabled: !!info,
    refetchInterval: info ? info.refresh * 1000 : false,
  })
  return { layers, info, data: info ? data.data : undefined, error: info && data.error ? data.error.message : '' }
}
