import { Badge, Button, Divider, Popover, SegmentedControl, Slider, Stack, Switch, Text } from '@mantine/core'
import { IconStack2 } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LAYERS, type LayerId, type LayerState, PRESETS, type PresetId, applyPreset, opacity, presetOf } from './layers'

/** The layer picker over the Seats view: presets, one switch per layer and how strong it is drawn.
 *  ``available`` leaves out what isn't set up (no power boards, no firewall ranges, …). */
export function LayersPanel({ state, onChange, available, legends, extra, onOpen }: {
  state: LayerState; onChange: (next: LayerState) => void; available: Record<LayerId, boolean>; legends?: LayerLegends
  /** Drawn under the plan's own layers: the plugin layer picker (./PluginLayer.tsx). */
  extra?: ReactNode
  /** Phones: the button opens the plan's side panel as a sheet instead of a popover. */
  onOpen?: () => void
}) {
  const { t } = useTranslation()
  const shown = LAYERS.filter((l) => state.on.has(l) && available[l]).length
  const button = (
    <Button size="xs" variant="default" leftSection={<IconStack2 size={14} />} onClick={onOpen}
      rightSection={<Badge size="xs" variant="light" circle>{shown}</Badge>}>
      {t('plan.layers.button')}
    </Button>
  )
  if (onOpen) return button
  // Never wider or taller than the screen: on a phone a 400 px popover lost its right edge.
  return (
    <Popover position="bottom-end" width="min(400px, calc(100vw - 16px))" shadow="md" withArrow>
      <Popover.Target>{button}</Popover.Target>
      <Popover.Dropdown aria-label={t('plan.layers.title')} className="fb-layers-pop">
        <LayersBody state={state} onChange={onChange} available={available} legends={legends} extra={extra} />
      </Popover.Dropdown>
    </Popover>
  )
}

/** What each layer draws, shown under its switch while it is on; ``seats`` under the seats line. */
export type LayerLegends = Partial<Record<LayerId | 'seats', ReactNode>>

/** The layer presets and switches themselves: in the Layers popover, or in the plan's side panel. */
export function LayersBody({ state, onChange, available, legends = {}, extra }: {
  state: LayerState; onChange: (next: LayerState) => void; available: Record<LayerId, boolean>; legends?: LayerLegends
  extra?: ReactNode
}) {
  const { t } = useTranslation()
  const preset = presetOf(state.on)
  const toggle = (id: LayerId, on: boolean) => {
    const next = new Set(state.on)
    if (on) next.add(id)
    else next.delete(id)
    onChange({ ...state, on: next })
  }
  const fade = (id: LayerId, pct: number) => {
    const next = { ...state.fade }
    if (pct >= 100) delete next[id]
    else next[id] = pct / 100
    onChange({ ...state, fade: next })
  }
  return (
    <Stack gap="xs">
      <Text size="xs" fw={700} tt="uppercase" c="dimmed">{t('plan.layers.presets')}</Text>
      <SegmentedControl size="xs" fullWidth value={preset ?? ''} aria-label={t('plan.layers.presets')}
        data={(Object.keys(PRESETS) as PresetId[]).map((p) => ({ value: p, label: t(`plan.layers.preset.${p}`) }))}
        onChange={(p) => onChange(applyPreset(state, p as PresetId))} />
      <Divider />
      <Text size="xs" c="dimmed">{t('plan.layers.seats')}</Text>
      {legends.seats && <div className="fb-layer-legend seats">{legends.seats}</div>}
      {LAYERS.map((id) => {
        const on = state.on.has(id) && available[id]
        return (
          <div key={id} className="fb-layers-row" data-layer={id}>
            <Switch size="sm" checked={on} disabled={!available[id]} onChange={(e) => toggle(id, e.currentTarget.checked)}
              label={t(`plan.layers.item.${id}`)} description={available[id] ? undefined : t('plan.layers.off')} />
            {on ? (
              <Slider size="xs" min={10} max={100} step={10} value={Math.round(opacity(state, id) * 100)} label={(v) => `${v} %`}
                onChange={(v) => fade(id, v)} thumbLabel={t('plan.layers.opacity', { layer: t(`plan.layers.item.${id}`) })} />
            ) : <span />}
            {on && legends[id] && <div className="fb-layer-legend">{legends[id]}</div>}
          </div>
        )
      })}
      {extra}
      <Text size="xs" c="dimmed">{t('plan.layers.hint')}</Text>
    </Stack>
  )
}
