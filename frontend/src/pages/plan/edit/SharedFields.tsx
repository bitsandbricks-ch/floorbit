import { ColorSwatch, Group, SegmentedControl, Select, Stack, Text, Tooltip } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { TintField } from './TintField'
import { LAYER_IDS, MIXED, type SharedField, ZONE_COLORS, ZONE_SWATCH } from './shared'

/** The fields several selected items share (``sharedFields``): picking a value sets it on all of
 *  them. A field whose items differ shows nothing picked. */
export function SharedFields({ fields, onChange }: {
  fields: Partial<Record<SharedField, unknown>>
  onChange: (field: SharedField, value: unknown) => void
}) {
  const { t } = useTranslation()
  const has = (f: SharedField) => f in fields
  const mixed = (f: SharedField) => fields[f] === MIXED
  const value = (f: SharedField) => (mixed(f) || fields[f] == null ? '' : String(fields[f]))
  if (!Object.keys(fields).length) return null
  const segments = (f: SharedField, label: string, data: { value: string; label: string }[]) => (
    <div>
      <Text size="sm" fw={500} mb={4}>{label}{mixed(f) && <Text span size="xs" c="dimmed" ml={6}>{t('plan.edit.mixed')}</Text>}</Text>
      <SegmentedControl fullWidth value={value(f)} data={data} onChange={(v) => onChange(f, f === 'rotation' ? Number(v) : v)} />
    </div>
  )
  return (
    <Stack gap="sm" role="group" aria-label={t('plan.edit.sharedFields')}>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed">{t('plan.edit.sharedFields')}</Text>
      {has('size') && segments('size', t('plan.edit.mark.size'), ['s', 'm', 'l'].map((x) => ({ value: x, label: t(`plan.edit.mark.sizes.${x}`) })))}
      {has('rotation') && segments('rotation', t('plan.edit.rotation'), ['0', '90', '180', '270'].map((v) => ({ value: v, label: `${v}°` })))}
      {has('style') && segments('style', t('plan.edit.style'), [{ value: 'solid', label: t('plan.edit.styles.solid') }, { value: 'dashed', label: t('plan.edit.styles.dashed') }])}
      {has('color') && (
        <div>
          <Text size="sm" fw={500} mb={4}>{t('plan.edit.color')}</Text>
          <Group gap="xs">
            {ZONE_COLORS.map((c) => (
              <Tooltip key={c} label={t(`plan.edit.colors.${c}`)}>
                <ColorSwatch component="button" type="button" color={ZONE_SWATCH[c]} size={26}
                  aria-label={t(`plan.edit.colors.${c}`)} aria-pressed={fields.color === c} onClick={() => onChange('color', c)}
                  style={{ outline: fields.color === c ? '2px solid var(--bnb-fg)' : undefined, outlineOffset: 2 }} />
              </Tooltip>
            ))}
          </Group>
        </div>
      )}
      {has('tint') && (
        <TintField key={String(fields.tint)} value={mixed('tint') || fields.tint == null ? null : String(fields.tint)} mixed={mixed('tint')}
          onChange={(v) => onChange('tint', v)} />
      )}
      {has('layer') && (
        <Select label={t('plan.edit.layer')} allowDeselect={false} value={mixed('layer') ? null : String(fields.layer)} placeholder={t('plan.edit.mixed')}
          onChange={(v) => v && onChange('layer', v)} data={LAYER_IDS.map((l) => ({ value: l, label: t(`plan.edit.layers.${l}`) }))} />
      )}
    </Stack>
  )
}
