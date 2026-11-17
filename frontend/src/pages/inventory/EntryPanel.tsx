import { Anchor, Button, Group, Select, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch } from '@/api/client'
import { qk } from '@/api/keys'
import type { EntryDetail, InventoryOverview, InventoryType } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Field, LoadingState, PanelSection, SidePanel } from '@/components/ui'
import { FieldInputs } from './FieldInputs'
import { DeviceIcon } from './icons'
import { typeName } from './model'
import { groupTree, useEntryDetail } from './scope'
import { LookFields, PropertiesEditor, TagPicker } from './ScopeEditors'

/** One cable, circuit, rack, ... with its fields and what it gets from its type, groups and tags. */
export function EntryPanel({ type, id, overview, canEdit, onClose }: {
  type: InventoryType; id: string; overview: InventoryOverview; canEdit: boolean; onClose: () => void
}) {
  const { t } = useTranslation()
  const { data: entry } = useEntryDetail(type.id, id)
  const icon = entry ? entry.resolved.look.icon.value || type.default_icon : type.default_icon
  const color = entry?.resolved.look.color.value ?? ''
  return (
    <SidePanel width={560} onClose={onClose}
      title={entry ? <Group gap="sm" wrap="nowrap"><DeviceIcon icon={icon} color={color} />{entry.name}</Group> : t('common.loading')}
      subtitle={entry && [typeName(t, type), ...entry.resolved.group_path.map((g) => g.name)].join(' · ')}>
      {!entry ? <LoadingState /> : <EntryForm key={JSON.stringify(entry)} type={type} entry={entry} overview={overview} canEdit={canEdit} onClose={onClose} />}
    </SidePanel>
  )
}

function EntryForm({ type, entry, overview, canEdit, onClose }: {
  type: InventoryType; entry: EntryDetail; overview: InventoryOverview; canEdit: boolean; onClose: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(entry.name)
  const [fields, setFields] = useState(entry.fields)
  const [groupId, setGroupId] = useState(entry.group_id)
  const [tags, setTags] = useState(entry.tags)
  const [icon, setIcon] = useState(entry.icon)
  const [color, setColor] = useState(entry.color)
  const [notes, setNotes] = useState(entry.notes)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const url = `/api/inventory/entries/${encodeURIComponent(type.id)}/${encodeURIComponent(entry.id)}`
  const refresh = () => qc.invalidateQueries({ queryKey: qk.inventoryAll })
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(url, body),
    onSuccess: () => { setMessage({ ok: true, text: t('inventory.saved') }); void refresh() },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const remove = useMutation({ mutationFn: () => del(url), onSuccess: () => { void refresh(); onClose() } })
  const stored = type.sort === 'stored'
  const changes: Record<string, unknown> = {}
  if (stored && name !== entry.name) changes.name = name
  if (JSON.stringify(fields) !== JSON.stringify(entry.fields)) changes.fields = Object.fromEntries(
    type.fields.map((f) => [f.key, fields[f.key] ?? '']).filter(([k, v]) => v !== (entry.fields[k] ?? '')))
  if (groupId !== entry.group_id) changes.group_id = groupId
  if (JSON.stringify(tags) !== JSON.stringify(entry.tags)) changes.tags = tags
  if (icon !== entry.icon) changes.icon = icon
  if (color !== entry.color) changes.color = color
  if (notes !== entry.notes) changes.notes = notes
  return (
    <Stack gap="md">
      {(entry.summary || entry.link) && (
        <PanelSection label={t('inventory.tabs.overview')}>
          <Stack gap={4}>
            {entry.summary && <Field label={t('inventory.entries.what')}>{entry.summary}</Field>}
            {entry.detail && <Text size="sm" c="dimmed">{entry.detail}</Text>}
            {entry.link && (
              <Anchor href={entry.link} size="sm">
                <Group gap={4} component="span">{t(`inventory.entries.openOn.${type.id}`, { defaultValue: t('inventory.entries.open') })}<IconExternalLink size={14} /></Group>
              </Anchor>
            )}
          </Stack>
        </PanelSection>
      )}
      <PanelSection label={t('inventory.entries.details')}>
        <Stack gap="sm">
          {stored && <TextInput label={t('inventory.field.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} disabled={!canEdit} maxLength={80} />}
          <FieldInputs fields={type.fields} values={fields} onChange={setFields} disabled={!canEdit} />
          <Select label={t('inventory.groups.one')} placeholder={t('inventory.groups.none')} clearable searchable disabled={!canEdit}
            data={groupTree(overview.groups).map(({ group, depth }) => ({ value: group.id, label: `${'  '.repeat(depth)}${group.name}` }))}
            value={groupId} onChange={setGroupId} />
          <TagPicker tags={overview.tags} value={tags} onChange={setTags} />
          <LookFields icon={icon} color={color} icons={overview.icons} onIcon={setIcon} onColor={setColor}
            inherited={{ icon: entry.resolved.look.icon.value || type.default_icon, color: entry.resolved.look.color.value }} />
          <Textarea label={t('inventory.field.notes')} value={notes} onChange={(e) => setNotes(e.currentTarget.value)} autosize minRows={2} maxLength={1000} disabled={!canEdit} />
          {message && <Text size="sm" role="status" className={message.ok ? 'fb-tone-ok' : 'fb-tone-err'}>{message.ok ? '✓' : '✕'} {message.text}</Text>}
          {canEdit && (
            <Group justify="space-between">
              {stored ? (
                <ConfirmButton variant="subtle" danger label={t('inventory.delete')} question={t('inventory.deleteManual', { name: entry.name })}
                  onConfirm={() => remove.mutate()} />
              ) : <span />}
              <Button loading={save.isPending} disabled={!Object.keys(changes).length} onClick={() => save.mutate(changes)}>{t('inventory.save')}</Button>
            </Group>
          )}
        </Stack>
      </PanelSection>
      <PanelSection label={t('inventory.props.title')}>
        <PropertiesEditor value={entry.properties} inherited={entry.resolved.properties} canEdit={canEdit} busy={save.isPending}
          onSave={(properties) => save.mutate({ properties })} />
      </PanelSection>
    </Stack>
  )
}
