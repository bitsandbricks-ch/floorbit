import { ActionIcon, Button, Group, Menu, Paper, Text } from '@mantine/core'
import { IconChevronDown, IconTerminal2, IconX } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Device, InventoryOverview } from '@/api/types'
import './PickBar.css'

export type BulkAction =
  | { action: 'tag-add' | 'tag-remove'; tag: string }
  | { action: 'group'; group_id: string | null }
  | { action: 'hide' | 'show' }

/** The bar over the inventory list once devices are picked (issue #980): tag, group, hide and the
 *  switch console for all of them at once, in one request each (POST /api/inventory/bulk). */
export function PickBar({ picked, overview, canEdit, canRun, onClear, onDone }: {
  picked: Device[]
  overview: InventoryOverview | undefined
  canEdit: boolean
  canRun: boolean
  onClear: () => void
  onDone: (text: string, ok: boolean) => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const bulk = useMutation({
    mutationFn: (a: BulkAction) => post<{ changed: string[]; unchanged: number }>('/api/inventory/bulk', { ids: picked.map((d) => d.id), ...a }),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: qk.inventoryAll })
      onDone(t('inventory.bulk.done', { count: res.changed.length }), true)
    },
    onError: (err) => onDone(t('common.error', { message: err.message }), false),
  })
  const tags = overview?.tags ?? []
  const onPicked = new Set(picked.flatMap((d) => d.tags ?? []))
  const groups = [...(overview?.groups ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  const switches = picked.filter((d) => d.role === 'switch').map((d) => d.name)
  const anyHidden = picked.some((d) => d.hidden)
  const anyShown = picked.some((d) => !d.hidden)
  const menu = (label: string, items: { key: string; label: string; run: () => void }[]) => (
    <Menu position="bottom-start" withinPortal>
      <Menu.Target>
        <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />} disabled={!items.length || bulk.isPending}>{label}</Button>
      </Menu.Target>
      <Menu.Dropdown mah={320} style={{ overflowY: 'auto' }}>
        {items.map((i) => <Menu.Item key={i.key} onClick={i.run}>{i.label}</Menu.Item>)}
      </Menu.Dropdown>
    </Menu>
  )
  return (
    <Paper withBorder shadow="md" p="xs" mt="sm" className="fb-pickbar" role="toolbar" aria-label={t('inventory.bulk.label')}>
      <Group gap="xs" wrap="wrap">
        <Text size="sm" fw={600} mr="xs">{t('inventory.bulk.picked', { count: picked.length })}</Text>
        {canRun && (
          <Button size="xs" variant="default" leftSection={<IconTerminal2 size={14} />} disabled={!switches.length}
            onClick={() => navigate(`/commands?${switches.map((s) => `switch=${encodeURIComponent(s)}`).join('&')}`)}>
            {t('inventory.bulk.run')}
          </Button>
        )}
        {canEdit && (
          <>
            {menu(t('inventory.bulk.tagAdd'), tags.map((x) => ({ key: x.id, label: x.name, run: () => bulk.mutate({ action: 'tag-add', tag: x.id }) })))}
            {menu(t('inventory.bulk.tagRemove'), tags.filter((x) => onPicked.has(x.id))
              .map((x) => ({ key: x.id, label: x.name, run: () => bulk.mutate({ action: 'tag-remove', tag: x.id }) })))}
            {menu(t('inventory.bulk.group'), [
              ...groups.map((x) => ({ key: x.id, label: x.name, run: () => bulk.mutate({ action: 'group', group_id: x.id }) })),
              { key: '', label: t('inventory.bulk.noGroup'), run: () => bulk.mutate({ action: 'group', group_id: null }) },
            ])}
            {anyShown && <Button size="xs" variant="default" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: 'hide' })}>{t('inventory.bulk.hide')}</Button>}
            {anyHidden && <Button size="xs" variant="default" disabled={bulk.isPending} onClick={() => bulk.mutate({ action: 'show' })}>{t('inventory.unhide')}</Button>}
          </>
        )}
        <ActionIcon variant="subtle" color="gray" ml="auto" onClick={onClear} aria-label={t('inventory.bulk.clear')}><IconX size={16} /></ActionIcon>
      </Group>
    </Paper>
  )
}
