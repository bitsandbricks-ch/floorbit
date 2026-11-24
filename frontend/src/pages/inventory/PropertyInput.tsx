import { Badge, MultiSelect, Select, Text, TextInput } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { PropertyDef } from '@/api/properties'
import { propHint, propLabel } from './propertyText'

/** The value input that fits a known property's type (#879); free text for one Floorbit doesn't know. */
export function PropertyInput({ def, value, disabled, onChange }: {
  def?: PropertyDef; value: string; disabled: boolean; onChange: (value: string) => void
}) {
  const { t } = useTranslation()
  const label = t('inventory.props.value')
  const style = { flex: 1 }
  if (def?.type === 'bool') {
    return (
      <Select aria-label={label} value={value || null} disabled={disabled} style={style} clearable
        data={[{ value: 'true', label: t('inventory.types.yes') }, { value: 'false', label: t('inventory.types.no') }]}
        onChange={(v) => onChange(v ?? '')} />
    )
  }
  if (def?.type === 'choice') {
    return <Select aria-label={label} value={value || null} disabled={disabled} style={style} clearable
      data={def.choices} onChange={(v) => onChange(v ?? '')} />
  }
  if (def?.type === 'list') {
    const picked = value.split(/[,\s]+/).filter((w) => def.choices.includes(w))
    return <MultiSelect aria-label={label} value={picked} disabled={disabled} style={style} clearable
      data={def.choices} onChange={(v) => onChange(v.join(', '))} />
  }
  return (
    <TextInput aria-label={label} value={value} disabled={disabled} style={style}
      inputMode={def?.type === 'number' ? 'decimal' : undefined}
      placeholder={def?.type === 'ip' ? '192.0.2.10' : def?.type === 'url' ? 'https://example.com' : undefined}
      rightSection={def?.unit ? <Text size="xs" c="dimmed">{def.unit}</Text> : undefined}
      onChange={(e) => onChange(e.currentTarget.value)} />
  )
}

/** What a property name stands for, under it: its label, or that Floorbit doesn't know it. */
export function PropertyNote({ def, name }: { def?: PropertyDef; name: string }) {
  const { t } = useTranslation()
  if (!name.trim()) return null
  if (!def) return <Badge size="xs" variant="light" color="gray" tt="none">{t('inventory.props.untyped')}</Badge>
  const hint = propHint(t, def)
  return <Text size="xs" c="dimmed">{propLabel(t, def)}{hint ? ` · ${hint}` : ''}</Text>
}
