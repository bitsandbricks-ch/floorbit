import { ActionIcon, Group, Kbd, Tooltip } from '@mantine/core'
import { IconGrid4x4, IconLayoutAlignCenter, IconMagnet, IconRuler2 } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { LayerState } from '../layers'
import { setSnapPrefs, useSnapPrefs } from './snap'

/** Edit mode's top bar toggles: show the grid (the grid layer), snap to it, snap to other items,
 *  and the rulers along the plan's edges. */
export function SnapToggles({ layers, onLayers }: { layers: LayerState; onLayers: (next: LayerState) => void }) {
  const { t } = useTranslation()
  const prefs = useSnapPrefs()
  const gridShown = layers.on.has('grid')
  const toggle = (label: string, on: boolean, Icon: typeof IconMagnet, onClick: () => void, keys?: string) => (
    <Tooltip label={keys ? <>{label} <Kbd size="xs">{keys}</Kbd></> : label}>
      <ActionIcon variant={on ? 'light' : 'default'} size="md" aria-label={label} aria-pressed={on} aria-keyshortcuts={keys?.replace(/ /g, '+')} onClick={onClick}>
        <Icon size={16} aria-hidden="true" />
      </ActionIcon>
    </Tooltip>
  )
  return (
    <Group gap={4} role="group" aria-label={t('plan.edit.snap.label')} wrap="nowrap">
      {toggle(t('plan.edit.snap.showGrid'), gridShown, IconGrid4x4, () => {
        const on = new Set(layers.on)
        if (gridShown) on.delete('grid'); else on.add('grid')
        onLayers({ ...layers, on })
      })}
      {toggle(t('plan.edit.snap.grid'), prefs.grid, IconMagnet, () => setSnapPrefs({ grid: !prefs.grid }))}
      {toggle(t('plan.edit.snap.items'), prefs.items, IconLayoutAlignCenter, () => setSnapPrefs({ items: !prefs.items }))}
      {toggle(t('plan.edit.snap.rulers'), prefs.rulers, IconRuler2, () => setSnapPrefs({ rulers: !prefs.rulers }))}
    </Group>
  )
}
