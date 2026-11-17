import { Select, SimpleGrid, TextInput } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { FieldDef } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'
import { useEntries } from './scope'

/** A type's fields as real inputs (number, choice, yes/no, a link picked from the inventory).
 *  An empty value shows the type's default as its placeholder. */
export function FieldInputs({ fields, values, onChange, disabled }: {
  fields: FieldDef[]; values: Record<string, string>; onChange: (values: Record<string, string>) => void; disabled?: boolean
}) {
  if (!fields.length) return null
  const set = (key: string) => (value: string | null) => onChange({ ...values, [key]: value ?? '' })
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
      {fields.map((f) => <FieldInput key={f.key} field={f} value={values[f.key] ?? ''} onChange={set(f.key)} disabled={disabled} />)}
    </SimpleGrid>
  )
}

function FieldInput({ field, value, onChange, disabled }: {
  field: FieldDef; value: string; onChange: (v: string | null) => void; disabled?: boolean
}) {
  const { t } = useTranslation()
  const label = t(`inventory.types.fieldLabel.${field.key}`, { defaultValue: field.label })
  const placeholder = field.default || undefined
  if (field.kind === 'choice' || field.kind === 'bool') {
    const data = field.kind === 'bool'
      ? [{ value: 'yes', label: t('inventory.types.yes') }, { value: 'no', label: t('inventory.types.no') }]
      : field.choices
    return <Select label={label} data={data} value={value || null} onChange={onChange} clearable disabled={disabled}
      placeholder={field.kind === 'bool' && placeholder ? t(`inventory.types.${placeholder}`) : placeholder} />
  }
  if (field.kind === 'link') return <LinkInput field={field} label={label} value={value} onChange={onChange} disabled={disabled} />
  return (
    <TextInput label={label} value={value} placeholder={placeholder} disabled={disabled} maxLength={200}
      inputMode={field.kind === 'number' ? 'decimal' : undefined}
      onChange={(e) => onChange(field.kind === 'number' ? e.currentTarget.value.replace(/[^\d.,-]/g, '') : e.currentTarget.value)} />
  )
}

function LinkInput({ field, label, value, onChange, disabled }: {
  field: FieldDef; label: string; value: string; onChange: (v: string | null) => void; disabled?: boolean
}) {
  const toDevice = !field.link || field.link === 'device'
  const { data } = useEntries(field.link, !toDevice)
  if (toDevice) return <EntitySelect kind="devices" label={label} value={value} onChange={(v) => onChange(v)} disabled={disabled} />
  const names = [...new Set((data?.entries ?? []).map((e) => e.name))]
  return <Select label={label} data={names} value={value || null} onChange={onChange} clearable searchable disabled={disabled} />
}
