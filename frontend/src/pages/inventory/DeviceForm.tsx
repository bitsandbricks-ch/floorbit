import { ActionIcon, Button, Collapse, Group, Modal, Select, Stack, Text, Textarea, TextInput, Tooltip } from '@mantine/core'
import { IconChevronDown, IconLock, IconLockOpen } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { INVENTORY_FIELDS, SPEC_FIELDS, type Device, type InventoryField, type InventoryOverview } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'
import { FieldInputs } from './FieldInputs'
import { DEVICE_STATUSES, draftOf, fedValue, SPEC_ROLES, statusLabel, type Draft } from './model'
import { groupTree, useInventoryTypes } from './scope'
import { LookFields, TagPicker } from './ScopeEditors'

/** Set by hand only, never fed: where the device sorts in and how it looks. */
interface Placement {
  group_id: string | null
  tags: string[]
  icon: string
  color: string
  fields: Record<string, string>
}

function placementOf(device: Device | null): Placement {
  return { group_id: device?.group_id ?? null, tags: device?.tags ?? [], icon: device?.icon ?? '', color: device?.color ?? '', fields: device?.fields ?? {} }
}

export function DeviceForm({
  device,
  roles,
  overview,
  sourceName,
  opened,
  busy,
  error,
  onClose,
  onSave,
  onUnlock,
}: {
  device: Device | null
  roles: string[]
  overview?: InventoryOverview
  sourceName: (id: string) => string
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (changes: Partial<Draft> & Partial<Placement>) => void
  onUnlock: (field: InventoryField) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Draft>(() => draftOf(device))
  const original = draftOf(device)
  const [place, setPlace] = useState<Placement>(() => placementOf(device))
  const placeBefore = placementOf(device)
  const deviceFields = useInventoryTypes().data?.types.find((x) => x.id === 'device')?.fields ?? []
  const [specsOpen, setSpecsOpen] = useState(() => SPEC_FIELDS.some((f) => !!device?.[f]))
  const showSpecs = specsOpen || SPEC_ROLES.includes(draft.role)
  const set = (f: InventoryField) => (value: string) => setDraft((d) => ({ ...d, [f]: value }))

  function lockFor(f: InventoryField) {
    if (!device || !device.locked.includes(f)) return null
    const fed = fedValue(device, f)
    if (!fed) return null
    const source = sourceName(fed.source)
    return (
      <Tooltip label={t('inventory.unlock', { source })}>
        <ActionIcon variant="subtle" color="warn" aria-label={t('inventory.unlock', { source })} onClick={() => onUnlock(f)} disabled={busy}>
          <IconLockOpen size={16} />
        </ActionIcon>
      </Tooltip>
    )
  }

  function hint(f: InventoryField) {
    if (!device || !device.locked.includes(f)) return undefined
    const fed = fedValue(device, f)
    if (!fed) return undefined
    return (
      <Group gap={4} component="span" wrap="nowrap">
        <IconLock size={12} aria-hidden="true" />
        {t('inventory.lockedHint', { source: sourceName(fed.source), value: fed.value || '–' })}
      </Group>
    )
  }

  const field = (f: InventoryField, extra: { mono?: boolean; required?: boolean; placeholder?: string; numeric?: boolean } = {}) => (
    <TextInput
      key={f}
      label={t(`inventory.field.${f}`)}
      value={draft[f]}
      onChange={(e) => set(f)(extra.numeric ? e.currentTarget.value.replace(/\D/g, '') : e.currentTarget.value)}
      inputMode={extra.numeric ? 'numeric' : undefined}
      description={hint(f)}
      rightSection={lockFor(f)}
      required={extra.required}
      placeholder={extra.placeholder}
      styles={extra.mono ? { input: { fontFamily: 'var(--font-mono)' } } : undefined}
      maxLength={f === 'mgmt_ip' ? 45 : 80}
    />
  )

  const placeChanges = Object.fromEntries(
    (Object.keys(place) as (keyof Placement)[]).filter((k) => JSON.stringify(place[k]) !== JSON.stringify(placeBefore[k])).map((k) => [k, place[k]]),
  )
  const changes = { ...Object.fromEntries(INVENTORY_FIELDS.filter((f) => draft[f] !== original[f]).map((f) => [f, draft[f]])), ...placeChanges }

  return (
    <Modal opened={opened} onClose={onClose} title={device ? t('inventory.edit', { name: device.name }) : t('inventory.newDevice')} size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave(device ? changes : { ...draft, ...place })
        }}
      >
        <Stack gap="sm">
          {field('name', { required: true })}
          <Select
            label={t('inventory.field.role')}
            data={roles.map((r) => ({ value: r, label: t(`inventory.role.${r}`, { defaultValue: r }) }))}
            value={draft.role}
            onChange={(v) => set('role')(v || 'other')}
            allowDeselect={false}
            description={hint('role')}
            rightSection={lockFor('role')}
          />
          <Group grow align="flex-start">
            {field('model')}
            {field('serial', { mono: true })}
          </Group>
          <Group grow align="flex-start">
            {field('mgmt_ip', { mono: true, placeholder: '192.0.2.10' })}
            {field('hall')}
          </Group>
          <Select
            label={t('inventory.field.status')}
            data={[
              { value: '', label: t('inventory.statusName.none') },
              ...[...DEVICE_STATUSES, ...(draft.status && !(DEVICE_STATUSES as readonly string[]).includes(draft.status) ? [draft.status] : [])]
                .map((s) => ({ value: s, label: statusLabel(t, s) })),
            ]}
            value={draft.status}
            onChange={(v) => set('status')(v ?? '')}
            allowDeselect={false}
            description={hint('status')}
            rightSection={lockFor('status')}
          />
          <Button variant="subtle" size="compact-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setSpecsOpen((o) => !o)}
            rightSection={<IconChevronDown size={14} style={{ transform: showSpecs ? 'rotate(180deg)' : undefined }} />}
            disabled={SPEC_ROLES.includes(draft.role)}>
            {t('inventory.specs')}
          </Button>
          <Collapse expanded={showSpecs}>
            <Stack gap="sm">
              <Group grow align="flex-start">
                {field('platform', { placeholder: 'nxos, proxmox, opnsense' })}
                {field('os')}
              </Group>
              <Group grow align="flex-start">
                {field('cpu')}
                {field('cores', { numeric: true })}
              </Group>
              <Group grow align="flex-start">
                {field('memory_mb', { numeric: true, placeholder: '16384' })}
                {field('disk_gb', { numeric: true, placeholder: '500' })}
              </Group>
              {(draft.role === 'vm' || draft.host) && (
                <EntitySelect kind="devices" label={t('inventory.field.host')} value={draft.host} onChange={set('host')}
                  description={hint('host') ?? t('inventory.hostHint')} rightSection={lockFor('host')} />
              )}
            </Stack>
          </Collapse>
          {overview && (
            <>
              <Select
                label={t('inventory.groups.one')}
                placeholder={t('inventory.groups.none')}
                data={groupTree(overview.groups).map(({ group, depth }) => ({ value: group.id, label: `${'\u00a0\u00a0'.repeat(depth)}${group.name}` }))}
                value={place.group_id}
                onChange={(v) => setPlace((p) => ({ ...p, group_id: v }))}
                clearable
                searchable
              />
              <TagPicker tags={overview.tags} value={place.tags} onChange={(tags) => setPlace((p) => ({ ...p, tags }))} />
              <FieldInputs fields={deviceFields} values={place.fields} onChange={(fields) => setPlace((p) => ({ ...p, fields }))} />
              <LookFields icon={place.icon} color={place.color} icons={overview.icons}
                onIcon={(icon) => setPlace((p) => ({ ...p, icon }))} onColor={(color) => setPlace((p) => ({ ...p, color }))} />
            </>
          )}
          <Textarea
            label={t('inventory.field.notes')}
            value={draft.notes}
            onChange={(e) => set('notes')(e.currentTarget.value)}
            autosize
            minRows={2}
            maxLength={1000}
          />
          {error && (
            <Text className="fb-tone-err" role="alert">
              ✕ {error}
            </Text>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={busy} disabled={!!device && Object.keys(changes).length === 0}>
              {t('inventory.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
