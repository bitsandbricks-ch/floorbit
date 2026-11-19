import { Button, Group, Select, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { CredentialInfo, InventoryGroup, InventoryOverview, InventoryTag } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Panel } from '@/components/ui'
import { credentialBody } from './model'
import { groupAndBelow, groupTree, useCredentials } from './scope'
import { TelemetryFields } from './TelemetryFields'
import { CredentialsEditor, FeaturesEditor, LookFields, PropertiesEditor, TagPicker, type CredentialDraft } from './ScopeEditors'

export type ScopeTarget = { kind: 'group'; item: InventoryGroup | null; parent?: string | null }
  | { kind: 'tag'; item: InventoryTag | null }
  | { kind: 'defaults' }

/** Edit a group, a tag or the defaults ("All devices"): what devices in it inherit. The body of
 *  their pages (ScopePage.tsx). */
export function ScopeEditor({ target, overview, onDeleted, onSaved }: {
  target: ScopeTarget; overview: InventoryOverview; onDeleted: () => void; onSaved: (target: ScopeTarget) => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const canSetCreds = useCan('settings.manage')
  const item = target.kind === 'defaults' ? null : target.item
  const group = target.kind === 'group' ? target.item : null
  const tag = target.kind === 'tag' ? target.item : null
  const [name, setName] = useState(item?.name ?? '')
  const [parent, setParent] = useState<string | null>(group?.parent_id ?? (target.kind === 'group' ? target.parent ?? null : null))
  const [icon, setIcon] = useState(item?.icon ?? '')
  const [color, setColor] = useState(item?.color ?? '')
  const [tags, setTags] = useState<string[]>(group?.tags ?? [])
  const [text, setText] = useState(group?.notes ?? tag?.description ?? '')
  const [error, setError] = useState<string | null>(null)
  const [credError, setCredError] = useState<string | null>(null)
  const creds = useCredentials(canEdit)
  const ownerType = target.kind
  const ownerId = target.kind === 'defaults' ? 'defaults' : item?.id ?? ''
  const own = (creds.data?.credentials ?? []).filter((c) => c.owner_type === ownerType && c.owner_id === ownerId)
  const refresh = () => client.invalidateQueries({ queryKey: qk.inventoryAll })

  const base = target.kind === 'group' ? '/api/inventory/groups' : target.kind === 'tag' ? '/api/inventory/tags' : '/api/inventory/defaults'
  const urlOf = (id: string) => `${base}/${encodeURIComponent(id)}`
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      target.kind === 'defaults' ? patch(base, body) : item ? patch<InventoryGroup>(urlOf(item.id), body) : post<InventoryGroup>(base, body),
    onSuccess: (saved) => {
      setError(null)
      void refresh()
      if (target.kind !== 'defaults' && !item) onSaved({ kind: target.kind, item: saved } as ScopeTarget)
    },
    onError: (e) => setError(e.message),
  })
  const remove = useMutation({
    mutationFn: () => del(urlOf(item?.id ?? '')),
    onSuccess: () => { void refresh(); onDeleted() },
    onError: (e) => setError(e.message),
  })
  const setCred = useMutation({
    mutationFn: (d: CredentialDraft) => put('/api/inventory/credentials', credentialBody(ownerType, ownerId, d)),
    onSuccess: () => { setCredError(null); void refresh() },
    onError: (e) => setCredError(e.message),
  })
  const removeCred = useMutation({
    mutationFn: (c: CredentialInfo) => del(`/api/inventory/credentials/${encodeURIComponent(c.id)}`),
    onSuccess: () => void refresh(),
    onError: (e) => setCredError(e.message),
  })

  const below = group ? groupAndBelow(overview.groups, group.id) : new Set<string>()
  const parents = groupTree(overview.groups).filter(({ group: g }) => !below.has(g.id))
    .map(({ group: g, depth }) => ({ value: g.id, label: `${'  '.repeat(depth)}${g.name}` }))
  const current = target.kind === 'defaults' ? overview.defaults : item

  function basics() {
    const body: Record<string, unknown> = { name, icon, color }
    if (target.kind === 'group') Object.assign(body, { parent_id: parent, tags, notes: text })
    if (target.kind === 'tag') body.description = text
    save.mutate(body)
  }

  return (
    <Stack gap="md">
      {target.kind !== 'defaults' && (
        <Panel title={t('inventory.groups.basics')}>
          <form onSubmit={(e) => { e.preventDefault(); basics() }}>
            <Stack gap="sm">
              <TextInput label={t('inventory.field.name')} required value={name} maxLength={60} disabled={!canEdit}
                onChange={(e) => setName(e.currentTarget.value)} />
              {target.kind === 'group' && (
                <Select label={t('inventory.groups.parent')} placeholder={t('inventory.groups.top')} data={parents} value={parent}
                  onChange={setParent} clearable searchable disabled={!canEdit} />
              )}
              <LookFields icon={icon} color={color} icons={overview.icons} onIcon={setIcon} onColor={setColor} />
              {target.kind === 'group' && <TagPicker tags={overview.tags} value={tags} onChange={setTags} />}
              <Textarea label={t(target.kind === 'group' ? 'inventory.field.notes' : 'inventory.tags.description')} value={text}
                autosize minRows={1} maxLength={target.kind === 'group' ? 1000 : 300} disabled={!canEdit}
                onChange={(e) => setText(e.currentTarget.value)} />
              {error && <Text className="fb-tone-err" role="alert">✕ {error}</Text>}
              {canEdit && (
                <Group justify="space-between">
                  {item ? (
                    <ConfirmButton size="xs" variant="subtle" danger label={t('inventory.delete')}
                      question={t(target.kind === 'group' ? 'inventory.groups.deleteQ' : 'inventory.tags.deleteQ', { name: item.name })}
                      onConfirm={() => remove.mutate()} />
                  ) : <span />}
                  <Button type="submit" loading={save.isPending} disabled={!name.trim()}>{item ? t('inventory.save') : t('inventory.groups.create')}</Button>
                </Group>
              )}
            </Stack>
          </form>
        </Panel>
      )}
      {current && (
        <>
          <Panel title={t('inventory.props.title')}>
            <PropertiesEditor key={JSON.stringify(current.properties)} value={current.properties} canEdit={canEdit}
              busy={save.isPending} onSave={(properties) => save.mutate({ properties })} />
          </Panel>
          <Panel title={t('inventory.features.title')}>
            <FeaturesEditor catalog={overview.features} value={current.features} canEdit={canEdit} busy={save.isPending}
              onSave={(features) => save.mutate({ features })} />
          </Panel>
          <Panel title={t('inventory.telemetry.how')} desc={t('inventory.telemetry.groupIntro')}>
            <TelemetryFields key={JSON.stringify(current.properties)} own={current.properties} canEdit={canEdit}
              busy={save.isPending} onSave={(properties) => save.mutate({ properties })} />
          </Panel>
          {canEdit && (
            <Panel title={t('inventory.creds.title')} desc={t('inventory.creds.inheritIntro')}>
              <CredentialsEditor own={own} overview={overview} canSet={canSetCreds} busy={setCred.isPending} error={credError}
                onSet={(d) => setCred.mutateAsync(d)} onRemove={(c) => removeCred.mutate(c)} />
            </Panel>
          )}
        </>
      )}
      {!current && <Text size="sm" c="dimmed">{t('inventory.groups.saveFirst')}</Text>}
    </Stack>
  )
}
