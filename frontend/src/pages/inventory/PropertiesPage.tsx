import { ActionIcon, Alert, Badge, Button, Group, MultiSelect, Paper, Select, SimpleGrid, Stack, TagsInput, Text, TextInput, Title } from '@mantine/core'
import { IconPencil, IconTags, IconTrash } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import { propertiesKey, usePropertyCatalog, type PropertyDef, type PropertyType } from '@/api/properties'
import { useCan } from '@/api/queries'
import { DataTable } from '@/components/DataTable'
import { propHint, propLabel } from './propertyText'
import { ItemPage } from '@/components/ItemPage'
import { ConfirmIcon } from '@bitsandbricks/ui'

const ROLES = ['switch', 'router', 'firewall', 'access-point', 'server', 'vm', 'pdu', 'other']
const TYPES: PropertyType[] = ['text', 'number', 'bool', 'ip', 'url', 'choice', 'list']
type Draft = { key: string; label: string; type: PropertyType; unit: string; choices: string[]; roles: string[]; hint: string }
const EMPTY: Draft = { key: '', label: '', type: 'text', unit: '', choices: [], roles: [], hint: '' }

/** The properties Floorbit knows, with the kind of value each takes, and the ones admins add (#879).
 *  /inventory/properties. A property nobody defined stays free text. */
export default function PropertiesPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canManage = useCan('settings.manage')
  const catalog = usePropertyCatalog()
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const done = () => { setEditing(null); setDraft(EMPTY); void qc.invalidateQueries({ queryKey: propertiesKey }) }
  const save = useMutation({
    mutationFn: () => editing ? patch<PropertyDef>(`/api/inventory/properties/${encodeURIComponent(editing)}`, draft)
      : post<PropertyDef>('/api/inventory/properties', draft),
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: (key: string) => del(`/api/inventory/properties/${encodeURIComponent(key)}`), onSuccess: done })
  const edit = (p: PropertyDef) => { setEditing(p.key); setDraft({ ...EMPTY, ...p }) }
  const typeLabel = (x: string) => t(`inventory.propTypes.${x}`)
  const choosing = draft.type === 'choice' || draft.type === 'list'

  return (
    <ItemPage title={t('inventory.propCatalog.title')} fallbackTitle={t('inventory.title')} icon={<IconTags size={26} />}
      back={{ href: '/inventory', label: t('inventory.page.back') }} loading={catalog.isPending}
      missing={catalog.error ? { title: t('inventory.page.notFound'), desc: catalog.error.message } : null}
      kicker={t('inventory.propCatalog.intro')}>
      <Stack gap="md">
        <DataTable rows={catalog.data?.properties ?? []} rowKey={(p) => p.key} label={t('inventory.propCatalog.title')} pageSize={0}
          urlState={false} cards
          columns={[
            { id: 'key', header: t('inventory.props.name'), sort: (p) => p.key, cell: (p) => (
              <>
                <Text size="sm" ff="monospace">{p.key}</Text>
                {p.builtin && <Badge size="xs" variant="light" color="gray" tt="none">{t('inventory.propCatalog.builtin')}</Badge>}
              </>
            ) },
            { id: 'label', header: t('inventory.propCatalog.label'), wrap: true, cell: (p) => (
              <>
                <Text size="sm">{propLabel(t, p)}</Text>
                {p.hint && <Text size="xs" c="dimmed">{propHint(t, p)}</Text>}
              </>
            ) },
            { id: 'type', header: t('inventory.propCatalog.type'), card: 'label', cell: (p) => `${typeLabel(p.type)}${p.unit ? ` (${p.unit})` : ''}` },
            { id: 'values', header: t('inventory.propCatalog.choices'), wrap: true, card: 'label', cell: (p) => p.choices.join(', ') || '–' },
            { id: 'roles', header: t('inventory.propCatalog.roles'), wrap: true, card: 'label', cell: (p) => p.roles.length
              ? p.roles.map((r) => t(`inventory.role.${r}`)).join(', ') : t('inventory.propCatalog.anyRole') },
            { id: 'actions', header: '', card: 'actions', width: 84, cell: (p) => !p.builtin && canManage && (
                <Group gap={2} wrap="nowrap">
                  <ActionIcon variant="subtle" color="gray" aria-label={t('inventory.propCatalog.edit')} onClick={() => edit(p)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ConfirmIcon variant="subtle" color="gray" label={t('inventory.propCatalog.remove')}
                    question={t('inventory.propCatalog.removeQ', { key: p.key })} onConfirm={() => remove.mutate(p.key)}>
                    <IconTrash size={16} />
                  </ConfirmIcon>
                </Group>
              ) },
          ]} />

        {canManage && (
          <Paper withBorder radius="lg" p="md">
            <Title order={2} size="h4" mb={4}>{editing ? t('inventory.propCatalog.editTitle', { key: editing }) : t('inventory.propCatalog.addTitle')}</Title>
            <Text size="sm" c="dimmed" mb="sm">{t('inventory.propCatalog.addHint')}</Text>
            <form onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
              <Stack gap="sm">
                {(save.error ?? remove.error) && <Alert color="down" role="alert">{(save.error ?? remove.error)!.message}</Alert>}
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <TextInput label={t('inventory.props.name')} placeholder="poe.budget" required value={draft.key} maxLength={40}
                    styles={{ input: { fontFamily: 'var(--font-mono)' } }} onChange={(e) => set('key')(e.currentTarget.value)} />
                  <TextInput label={t('inventory.propCatalog.label')} placeholder="PoE budget" value={draft.label} maxLength={60}
                    onChange={(e) => set('label')(e.currentTarget.value)} />
                  <Select label={t('inventory.propCatalog.type')} value={draft.type} allowDeselect={false}
                    data={TYPES.map((x) => ({ value: x, label: typeLabel(x) }))} onChange={(v) => set('type')((v ?? 'text') as PropertyType)} />
                  <TextInput label={t('inventory.propCatalog.unit')} placeholder="W" value={draft.unit} maxLength={16}
                    onChange={(e) => set('unit')(e.currentTarget.value)} />
                  {choosing && (
                    <TagsInput label={t('inventory.propCatalog.choices')} value={draft.choices} required
                      description={t('inventory.propCatalog.choicesHint')} onChange={set('choices')} />
                  )}
                  <MultiSelect label={t('inventory.propCatalog.roles')} placeholder={t('inventory.propCatalog.anyRole')} value={draft.roles}
                    data={ROLES.map((r) => ({ value: r, label: t(`inventory.role.${r}`) }))} onChange={set('roles')} clearable />
                </SimpleGrid>
                <TextInput label={t('inventory.propCatalog.hint')} value={draft.hint} maxLength={200} onChange={(e) => set('hint')(e.currentTarget.value)} />
                <Group justify="flex-end">
                  {editing && <Button variant="default" onClick={() => { setEditing(null); setDraft(EMPTY) }}>{t('common.cancel')}</Button>}
                  <Button type="submit" loading={save.isPending} disabled={!draft.key.trim()}>
                    {editing ? t('inventory.propCatalog.save') : t('inventory.propCatalog.add')}
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>
        )}
      </Stack>
    </ItemPage>
  )
}
