import { Switch, Text } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { patch } from '@/api/client'
import { qk } from '@/api/keys'
import type { InventoryEntry, InventoryType } from '@/api/types'

/** A yes/no field in an entry list: a switch for who may edit (the check-in lookups of a prefix or
 *  range, docs/segments.md), else Yes or No. */
export function BoolCell({ type, entry, field, canEdit }: {
  type: InventoryType; entry: InventoryEntry; field: { key: string; label: string; default: string }; canEdit: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const on = (entry.fields[field.key] || field.default) === 'yes'
  const save = useMutation({
    mutationFn: (value: boolean) => patch(`/api/inventory/entries/${encodeURIComponent(type.id)}/${encodeURIComponent(entry.id)}`,
      { fields: { [field.key]: value } }),
    onSettled: () => qc.invalidateQueries({ queryKey: qk.inventoryEntries(type.id) }),
  })
  const label = t(`inventory.types.fieldLabel.${field.key}`, { defaultValue: field.label })
  if (!canEdit) return <Text size="sm">{on ? t('inventory.types.yes') : t('inventory.types.no')}</Text>
  return (
    <Switch size="sm" checked={save.isPending ? !!save.variables : on} disabled={save.isPending}
      aria-label={`${label}: ${entry.name}`} onChange={(e) => save.mutate(e.currentTarget.checked)} />
  )
}
