import { Group, Select, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { PluginLayerData, PluginLayerInfo } from '@/api/types'
import { layerKey as keyOf } from './pluginLayerQuery'

/** The plugin layer picker and its legend, under the plan's own layers. Nothing when no plugin has one. */
export function PluginLayerPicker({ layers, value, onChange, data, error }: {
  layers: PluginLayerInfo[]; value: string | null; onChange: (next: string | null) => void
  data?: PluginLayerData; error?: string
}) {
  const { t } = useTranslation()
  if (!layers.length) return null
  return (
    <Stack gap={6} className="fb-plugin-layer">
      <Select size="xs" clearable label={t('plan.layers.plugin')} placeholder={t('plan.layers.pluginNone')}
        data={layers.map((l) => ({ value: keyOf(l), label: `${l.plugin_name}: ${l.label}` }))}
        value={value && layers.some((l) => keyOf(l) === value) ? value : null} onChange={onChange} />
      {error && <Text size="xs" className="fb-tone-err" role="alert">{error}</Text>}
      {data && data.legend.length > 0 && (
        <Group gap="sm" aria-label={t('plan.layers.pluginLegend')}>
          {data.legend.map((l, i) => (
            <Group key={i} gap={4} wrap="nowrap">
              <span className={`fb-pl-swatch pl-${l.tone}`} aria-hidden />
              <Text size="xs">{l.label}</Text>
            </Group>
          ))}
        </Group>
      )}
    </Stack>
  )
}
