import { Alert, Anchor, Badge, Button, Group, Modal, Paper, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconPlus, IconSearch } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { InventoryEntry, InventoryOverview, InventoryType } from '@/api/types'
import { LoadingState } from '@/components/ui'
import type { GroupFilter } from './GroupTree'
import { BoolCell } from './BoolCell'
import { DeviceIcon } from './icons'
import { effectiveLook, typeName } from './model'
import { groupAndBelow, useEntries } from './scope'

/** Every entry of one type (cables, circuits, racks, ...), filtered by the group tree and tags. */
export function EntriesView({ type, overview, group, tags, canEdit, onOpen, sourceName }: {
  type: InventoryType; overview: InventoryOverview; group: GroupFilter; tags: string[]; canEdit: boolean
  onOpen: (id: string) => void; sourceName: (id: string) => string
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const { data, isPending, error } = useEntries(type.id)
  const groups = overview.groups
  const inGroup = group && group !== 'none' ? groupAndBelow(groups, group) : null
  const shown = type.fields.slice(0, 3)
  const q = query.trim().toLowerCase()
  const entries = (data?.entries ?? []).filter((e) => {
    if (q && ![e.name, e.summary, e.detail, e.notes, ...Object.values(e.fields)].some((v) => (v || '').toLowerCase().includes(q))) return false
    if (group === 'none' && e.group_id) return false
    if (inGroup && !(e.group_id && inGroup.has(e.group_id))) return false
    if (tags.length && !tags.every((tid) => effectiveLook(e, groups).tags.has(tid))) return false
    return true
  })
  const value = (e: InventoryEntry, key: string) => e.fields[key] || type.fields.find((f) => f.key === key)?.default || ''
  return (
    <>
      <Group gap="sm" mb="md" align="flex-end">
        <TextInput label={t('inventory.search')} leftSection={<IconSearch size={16} />} value={query}
          onChange={(e) => setQuery(e.currentTarget.value)} style={{ flex: '1 1 260px' }} />
        {canEdit && type.sort === 'stored' && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            {t('inventory.entries.add', { type: typeName(t, type) })}
          </Button>
        )}
      </Group>
      {type.sort === 'linked' && <Text size="sm" c="dimmed" mb="xs">{t(`inventory.entries.linkedHint.${type.id}`)}</Text>}
      {isPending && <LoadingState />}
      {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
      {data && (
        <>
          <Text size="sm" c="dimmed" mb="xs">{t('inventory.entries.count', { count: entries.length })}</Text>
          {entries.length === 0 ? <Text>{data.entries.length ? t('inventory.noMatch') : t('inventory.entries.empty')}</Text> : (
            <Paper withBorder radius="lg">
              <Table.ScrollContainer minWidth={640}>
                <Table highlightOnHover verticalSpacing="xs" fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th w={36} />
                      <Table.Th>{t('inventory.field.name')}</Table.Th>
                      {type.sort === 'linked' && <Table.Th>{t('inventory.entries.what')}</Table.Th>}
                      {shown.map((f) => <Table.Th key={f.key}>{t(`inventory.types.fieldLabel.${f.key}`, { defaultValue: f.label })}</Table.Th>)}
                      <Table.Th>{t('inventory.groups.one')}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {entries.map((e) => {
                      const look = effectiveLook(e, groups)
                      return (
                        <Table.Tr key={e.id}>
                          <Table.Td><DeviceIcon icon={look.icon || type.icon || type.default_icon} color={look.color || type.color} size={24} /></Table.Td>
                          <Table.Td>
                            <Group gap={6} wrap="nowrap">
                              <Anchor component="button" type="button" fw={600} ta="left" onClick={() => onOpen(e.id)}>{e.name}</Anchor>
                              {e.sources?.map((s) => (
                                <Badge key={s} size="xs" variant={e.gone?.includes(s) ? 'outline' : 'light'} color={e.gone?.includes(s) ? 'warn' : 'trace'} tt="none">
                                  {e.gone?.includes(s) ? t('inventory.gone', { source: sourceName(s) }) : sourceName(s)}
                                </Badge>
                              ))}
                            </Group>
                            {e.tags.length > 0 && (
                              <Group gap={4} mt={2}>
                                {e.tags.map((tid) => {
                                  const tag = overview.tags.find((x) => x.id === tid)
                                  return tag && <Badge key={tid} size="xs" tt="none" variant="light" color={tag.color || 'gray'}>{tag.name}</Badge>
                                })}
                              </Group>
                            )}
                          </Table.Td>
                          {type.sort === 'linked' && <Table.Td>{e.summary}{e.detail && <Text size="xs" c="dimmed">{e.detail}</Text>}</Table.Td>}
                          {shown.map((f) => <Table.Td key={f.key}>{f.kind === 'bool'
                            ? <BoolCell type={type} entry={e} field={f} canEdit={canEdit} />
                            : value(e, f.key)}</Table.Td>)}
                          <Table.Td>{groups.find((g) => g.id === e.group_id)?.name ?? ''}</Table.Td>
                        </Table.Tr>
                      )
                    })}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
          )}
        </>
      )}
      {adding && <AddEntry type={type} onClose={() => setAdding(false)} onAdded={(id) => { setAdding(false); onOpen(id) }} />}
    </>
  )
}

function AddEntry({ type, onClose, onAdded }: { type: InventoryType; onClose: () => void; onAdded: (id: string) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const add = useMutation({
    mutationFn: () => post<InventoryEntry>(`/api/inventory/entries/${encodeURIComponent(type.id)}`, { name }),
    onSuccess: (e) => { void qc.invalidateQueries({ queryKey: qk.inventoryAll }); onAdded(e.id) },
  })
  return (
    <Modal opened onClose={onClose} title={t('inventory.entries.add', { type: typeName(t, type) })}>
      <form onSubmit={(e) => { e.preventDefault(); add.mutate() }}>
        <Stack gap="sm">
          <TextInput label={t('inventory.field.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} required data-autofocus maxLength={80} />
          {add.error && <Alert color="down" role="alert">{add.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={add.isPending} disabled={!name.trim()}>{t('inventory.groups.create')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
