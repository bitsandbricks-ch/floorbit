import { Badge, Button, Divider, Popover, SegmentedControl, Slider, Stack, Switch, Text } from '@mantine/core'
import { IconStack2 } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { LAYERS, type LayerId, type LayerState, PRESETS, type PresetId, opacity, presetOf } from './layers'

/** The layer picker over the Seats view: presets, one switch per layer and how strong it is drawn.
 *  ``available`` leaves out what isn't set up (no power boards, no firewall ranges, …). */
export function LayersPanel({ state, onChange, available }: {
  state: LayerState; onChange: (next: LayerState) => void; available: Record<LayerId, boolean>
}) {
  const { t } = useTranslation()
  const preset = presetOf(state.on)
  const shown = LAYERS.filter((l) => state.on.has(l) && available[l]).length
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
    <Popover position="bottom-end" width={400} shadow="md" withArrow>
      <Popover.Target>
        <Button size="xs" variant="default" leftSection={<IconStack2 size={14} />}
          rightSection={<Badge size="xs" variant="light" circle>{shown}</Badge>}>
          {t('plan.layers.button')}
        </Button>
      </Popover.Target>
      <Popover.Dropdown aria-label={t('plan.layers.title')}>
        <Stack gap="xs">
          <Text size="xs" fw={700} tt="uppercase" c="dimmed">{t('plan.layers.presets')}</Text>
          <SegmentedControl size="xs" fullWidth value={preset ?? ''} aria-label={t('plan.layers.presets')}
            data={(Object.keys(PRESETS) as PresetId[]).map((p) => ({ value: p, label: t(`plan.layers.preset.${p}`) }))}
            onChange={(p) => onChange({ on: new Set(PRESETS[p as PresetId]), fade: state.fade })} />
          <Divider />
          <Text size="xs" c="dimmed">{t('plan.layers.seats')}</Text>
          {LAYERS.map((id) => {
            const on = state.on.has(id) && available[id]
            return (
              <div key={id} className="fb-layers-row" data-layer={id}>
                <Switch size="sm" checked={on} disabled={!available[id]} onChange={(e) => toggle(id, e.currentTarget.checked)}
                  label={t(`plan.layers.item.${id}`)} description={available[id] ? undefined : t('plan.layers.off')} />
                {on ? (
                  <Slider size="xs" min={10} max={100} step={10} value={Math.round(opacity(state, id) * 100)} label={(v) => `${v} %`}
                    onChange={(v) => fade(id, v)} thumbProps={{ 'aria-label': t('plan.layers.opacity', { layer: t(`plan.layers.item.${id}`) }) }} />
                ) : <span />}
              </div>
            )
          })}
          <Text size="xs" c="dimmed">{t('plan.layers.hint')}</Text>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  )
}
