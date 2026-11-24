import { Anchor, Group, Select, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch } from '@/api/client'
import { qk } from '@/api/keys'
import type { EntryDetail, InventoryOverview, InventoryType } from '@/api/types'
import { DangerZone, ItemPage } from '@/components/ItemPage'
import { Field, Panel } from '@/components/ui'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { SaveBar } from '@/pages/settings/editor'
import { useCan } from '@/api/queries'
import { FieldInputs } from './FieldInputs'
import { DeviceIcon } from './icons'
import { typeName } from './model'
import { groupTree, useEntryDetail, useInventoryGroups, useInventoryTypes } from './scope'
import { LookFields, PropertiesEditor, TagPicker } from './ScopeEditors'

/** One cable, circuit, rack, ... on its own page (/inventory/entries/<type>/<id>): its fields and
 *  what it gets from its type, groups and tags. */
export default function EntryPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const params = useParams()
  const typeId = params.type ?? ''
  const id = params.id ?? ''
  const canEdit = useCan('floorplan.edit')
  const type = useInventoryTypes().data?.types.find((x) => x.id === typeId)
  const overview = useInventoryGroups().data
  const { data: entry, error } = useEntryDetail(typeId, id)
  const icon = entry ? entry.resolved.look.icon.value || type?.default_icon || 'other' : type?.default_icon ?? 'other'
  const color = entry?.resolved.look.color.value ?? ''
  return (
    <ItemPage title={entry && type && overview ? entry.name : undefined} fallbackTitle={t('inventory.title')}
      back={{ href: type ? `/inventory?type=${encodeURIComponent(type.id)}` : '/inventory', label: t('inventory.page.back') }}
      loading={!entry || !type || !overview} missing={error ? { title: t('inventory.page.notFound'), desc: error.message } : null}
      icon={<DeviceIcon icon={icon} color={color} size={28} />}
      kicker={entry && type ? [typeName(t, type), ...entry.resolved.group_path.map((g) => g.name)].join(' · ') : undefined}>
      {entry && type && overview && (
        <EntryForm key={JSON.stringify(entry)} type={type} entry={entry} overview={overview} canEdit={canEdit}
          onClose={() => navigate(`/inventory?type=${encodeURIComponent(type.id)}`)} />
      )}
    </ItemPage>
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
  useLeaveWarning(Object.keys(changes).length > 0)
  const discard = () => {
    setName(entry.name); setFields(entry.fields); setGroupId(entry.group_id); setTags(entry.tags)
    setIcon(entry.icon); setColor(entry.color); setNotes(entry.notes); setMessage(null)
  }
  return (
    <Stack gap="md">
      {(entry.summary || entry.link) && (
        <Panel title={t('inventory.tabs.overview')}>
          <Stack gap={4}>
            {entry.summary && <Field label={t('inventory.entries.what')}>{entry.summary}</Field>}
            {entry.detail && <Text size="sm" c="dimmed">{entry.detail}</Text>}
            {entry.link && (
              <Anchor href={entry.link} size="sm">
                <Group gap={4} component="span">{t(`inventory.entries.openOn.${type.id}`, { defaultValue: t('inventory.entries.open') })}<IconExternalLink size={14} /></Group>
              </Anchor>
            )}
          </Stack>
        </Panel>
      )}
      <Panel title={t('inventory.entries.details')}>
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
          {canEdit && (
            <SaveBar count={Object.keys(changes).length} saving={save.isPending} onSave={() => save.mutate(changes)}
              error={message && !message.ok ? new Error(message.text) : null} saved={message?.ok ? message.text : null}
              onDiscard={discard} />
          )}
        </Stack>
      </Panel>
      <Panel title={t('inventory.props.title')}>
        <PropertiesEditor value={entry.properties} inherited={entry.resolved.properties} canEdit={canEdit} busy={save.isPending}
          onSave={(properties) => save.mutate({ properties })} />
      </Panel>
      {canEdit && stored && (
        <DangerZone label={t('inventory.delete')} question={t('inventory.deleteManual', { name: entry.name })}
          loading={remove.isPending} onConfirm={() => remove.mutate()} />
      )}
    </Stack>
  )
}
