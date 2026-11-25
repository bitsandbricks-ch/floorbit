import { ActionIcon, Alert, Badge, Button, Grid, Group, Modal, NavLink, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SaveBar } from '@/pages/settings/editor'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { FieldDef, InventoryOverview, InventoryType } from '@/api/types'
import { ConfirmButton, PanelSection } from '@bitsandbricks/ui'
import { DeviceIcon } from './icons'
import { typeName } from './model'
import { useInventoryTypes } from './scope'
import { LookFields, PropertiesEditor } from './ScopeEditors'

const KINDS = ['text', 'number', 'choice', 'bool', 'link'] as const

/** Admins set up what each type of entry has: its fields, and what all its entries inherit. */
export function TypesEditor({ opened, overview, start = 'device', onClose }: {
  opened: boolean; overview: InventoryOverview; start?: string; onClose: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data } = useInventoryTypes()
  const [selected, setSelected] = useState(start)
  const [newName, setNewName] = useState('')
  const types = data?.types ?? []
  const type = types.find((x) => x.id === selected) ?? types[0]
  const create = useMutation({
    mutationFn: () => post<InventoryType>('/api/inventory/types', { name: newName }),
    onSuccess: (x) => { setNewName(''); setSelected(x.id); void qc.invalidateQueries({ queryKey: qk.inventoryAll }) },
  })
  return (
    <Modal opened={opened} onClose={onClose} title={t('inventory.types.title')} size="xl">
      <Text size="sm" c="dimmed" mb="sm">{t('inventory.types.intro')}</Text>
      <Grid>
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Stack gap={2}>
            {types.map((x) => (
              <NavLink key={x.id} active={x.id === type?.id} variant="light" label={typeName(t, x)} onClick={() => setSelected(x.id)}
                leftSection={<DeviceIcon icon={x.icon || x.default_icon} color={x.color} size={22} />}
                rightSection={<Badge size="xs" variant="light">{x.count}</Badge>} />
            ))}
            <form onSubmit={(e) => { e.preventDefault(); create.mutate() }}>
              <Group gap={4} mt="xs" wrap="nowrap">
                <TextInput size="xs" placeholder={t('inventory.types.newPlaceholder')} value={newName} maxLength={40}
                  aria-label={t('inventory.types.new')} onChange={(e) => setNewName(e.currentTarget.value)} style={{ flex: 1 }} />
                <ActionIcon type="submit" variant="light" aria-label={t('inventory.types.new')} loading={create.isPending} disabled={!newName.trim()}>
                  <IconPlus size={16} />
                </ActionIcon>
              </Group>
            </form>
            {create.error && <Text size="xs" className="fb-tone-err">{create.error.message}</Text>}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 8 }}>
          {type && <TypeForm key={JSON.stringify(type)} type={type} types={types} overview={overview} onRemoved={() => setSelected('device')} />}
        </Grid.Col>
      </Grid>
    </Modal>
  )
}

function TypeForm({ type, types, overview, onRemoved }: {
  type: InventoryType; types: InventoryType[]; overview: InventoryOverview; onRemoved: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(type.name)
  const [icon, setIcon] = useState(type.icon)
  const [color, setColor] = useState(type.color)
  const [fields, setFields] = useState<FieldDef[]>(type.own_fields)
  const [saved, setSaved] = useState(false)
  const url = `/api/inventory/types/${encodeURIComponent(type.id)}`
  const refresh = () => qc.invalidateQueries({ queryKey: qk.inventoryAll })
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(url, body),
    onSuccess: () => { setSaved(true); void refresh() },
  })
  const remove = useMutation({ mutationFn: () => del(url), onSuccess: () => { void refresh(); onRemoved() } })
  const fixed = type.fields.slice(0, type.fields.length - type.own_fields.length)
  const body: Record<string, unknown> = {}
  if (!type.builtin && name !== type.name) body.name = name
  if (icon !== type.icon) body.icon = icon
  if (color !== type.color) body.color = color
  if (JSON.stringify(fields) !== JSON.stringify(type.own_fields)) body.fields = fields
  const setField = (i: number, patchIt: Partial<FieldDef>) => { setSaved(false); setFields(fields.map((f, j) => (j === i ? { ...f, ...patchIt } : f))) }
  return (
    <Stack gap="md">
      <PanelSection label={t('inventory.types.basics')}>
        <Stack gap="sm">
          {!type.builtin && <TextInput label={t('inventory.field.name')} value={name} maxLength={40} onChange={(e) => setName(e.currentTarget.value)} />}
          <LookFields icon={icon} color={color} icons={overview.icons} onIcon={setIcon} onColor={setColor}
            inherited={{ icon: type.default_icon, color: '' }} />
        </Stack>
      </PanelSection>
      <PanelSection label={t('inventory.types.fields')}>
        <Stack gap="xs">
          {fixed.map((f) => (
            <Text key={f.key} size="sm">
              {t(`inventory.types.fieldLabel.${f.key}`, { defaultValue: f.label })}{' '}
              <Text span size="xs" c="dimmed">{t(`inventory.types.kinds.${f.kind}`)} · {t('inventory.types.builtIn')}</Text>
            </Text>
          ))}
          {fields.map((f, i) => (
            <Group key={i} gap="xs" align="flex-end" wrap="wrap">
              <TextInput size="xs" label={t('inventory.types.fieldName')} value={f.label} maxLength={40} style={{ flex: '1 1 140px' }}
                onChange={(e) => setField(i, { label: e.currentTarget.value })} />
              <Select size="xs" label={t('inventory.types.kind')} w={120} allowDeselect={false} value={f.kind}
                data={KINDS.map((k) => ({ value: k, label: t(`inventory.types.kinds.${k}`) }))}
                onChange={(v) => setField(i, { kind: (v ?? 'text') as FieldDef['kind'], default: '' })} />
              {f.kind === 'choice' && (
                <TextInput size="xs" label={t('inventory.types.choices')} placeholder="A, B, C" style={{ flex: '1 1 140px' }}
                  value={f.choices.join(', ')} onChange={(e) => setField(i, { choices: e.currentTarget.value.split(',').map((c) => c.trimStart()) })} />
              )}
              {f.kind === 'link' && (
                <Select size="xs" label={t('inventory.types.linkTo')} w={150} allowDeselect={false} value={f.link || 'device'}
                  data={types.map((x) => ({ value: x.id, label: typeName(t, x) }))} onChange={(v) => setField(i, { link: v ?? 'device' })} />
              )}
              {f.kind !== 'link' && (
                f.kind === 'bool' || f.kind === 'choice' ? (
                  <Select size="xs" label={t('inventory.types.default')} w={120} clearable value={f.default || null}
                    data={f.kind === 'bool' ? [{ value: 'yes', label: t('inventory.types.yes') }, { value: 'no', label: t('inventory.types.no') }]
                      : f.choices.map((c) => c.trim()).filter(Boolean)}
                    onChange={(v) => setField(i, { default: v ?? '' })} />
                ) : (
                  <TextInput size="xs" label={t('inventory.types.default')} w={120} value={f.default} maxLength={200}
                    onChange={(e) => setField(i, { default: e.currentTarget.value })} />
                )
              )}
              <ActionIcon variant="subtle" color="down" aria-label={t('inventory.props.remove', { name: f.label })}
                onClick={() => { setSaved(false); setFields(fields.filter((_, j) => j !== i)) }}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
          <Button size="xs" variant="subtle" leftSection={<IconPlus size={14} />} style={{ alignSelf: 'flex-start' }}
            onClick={() => setFields([...fields, { key: '', label: '', kind: 'text', choices: [], default: '', link: '' }])}>
            {t('inventory.types.addField')}
          </Button>
        </Stack>
      </PanelSection>
      {remove.error && <Alert color="down" role="alert">{remove.error.message}</Alert>}
      {!type.builtin && (
        <Group>
          <ConfirmButton variant="subtle" danger label={t('inventory.types.remove')} disabled={type.count > 0}
            question={t('inventory.types.removeQ', { name: type.name })} onConfirm={() => remove.mutate()} />
        </Group>
      )}
      {/* The shared bar (#993): "N unsaved changes, Discard, Save", then "Saved". */}
      <SaveBar count={Object.keys(body).length} bad={!type.builtin && !name.trim()} saving={save.isPending} error={save.error}
        saved={saved && !Object.keys(body).length ? t('inventory.saved') : null}
        onDiscard={() => { setName(type.name); setIcon(type.icon); setColor(type.color); setFields(type.own_fields) }}
        onSave={() => save.mutate({ ...body, ...(body.fields ? { fields: fields.map((f) => ({ ...f, choices: f.choices.map((c) => c.trim()).filter(Boolean) })) } : {}) })} />
      <PanelSection label={t('inventory.types.inherit')}>
        <PropertiesEditor value={type.properties} canEdit busy={save.isPending} onSave={(properties) => save.mutate({ properties })} />
      </PanelSection>
    </Stack>
  )
}
