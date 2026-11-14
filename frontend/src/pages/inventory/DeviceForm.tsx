import { ActionIcon, Button, Group, Modal, Select, Stack, Text, Textarea, TextInput, Tooltip } from '@mantine/core'
import { IconLock, IconLockOpen } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { INVENTORY_FIELDS, type Device, type InventoryField } from '@/api/types'
import { draftOf, fedValue, type Draft } from './model'

export function DeviceForm({
  device,
  roles,
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
  sourceName: (id: string) => string
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (changes: Partial<Draft>) => void
  onUnlock: (field: InventoryField) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Draft>(() => draftOf(device))
  const original = draftOf(device)
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

  const field = (f: InventoryField, extra: { mono?: boolean; required?: boolean; placeholder?: string } = {}) => (
    <TextInput
      key={f}
      label={t(`inventory.field.${f}`)}
      value={draft[f]}
      onChange={(e) => set(f)(e.currentTarget.value)}
      description={hint(f)}
      rightSection={lockFor(f)}
      required={extra.required}
      placeholder={extra.placeholder}
      styles={extra.mono ? { input: { fontFamily: 'var(--font-mono)' } } : undefined}
      maxLength={f === 'mgmt_ip' ? 45 : 80}
    />
  )

  const changes = Object.fromEntries(INVENTORY_FIELDS.filter((f) => draft[f] !== original[f]).map((f) => [f, draft[f]]))

  return (
    <Modal opened={opened} onClose={onClose} title={device ? t('inventory.edit', { name: device.name }) : t('inventory.newDevice')} size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave(device ? changes : draft)
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
          {field('status', { placeholder: 'active' })}
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
