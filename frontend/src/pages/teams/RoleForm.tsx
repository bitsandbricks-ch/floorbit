import { Button, Checkbox, Group, Modal, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { RoleInfo, RolesList } from '@/api/types'

export interface RoleDraft {
  id: string
  label: string
  description: string
  permissions: string[]
}

/** Add or change a custom role. Built-in roles are read-only and never open this. */
export function RoleForm({
  role,
  permissions,
  opened,
  busy,
  error,
  onClose,
  onSave,
}: {
  role: RoleInfo | null
  permissions: RolesList['permissions']
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (draft: RoleDraft) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<RoleDraft>({
    id: role?.id ?? '',
    label: role?.label ?? '',
    description: role?.description ?? '',
    permissions: role?.permissions ?? ['floorplan.view'],
  })
  const toggle = (p: string, on: boolean) =>
    setDraft((d) => ({ ...d, permissions: on ? [...d.permissions, p] : d.permissions.filter((x) => x !== p) }))

  return (
    <Modal opened={opened} onClose={onClose} title={role ? t('teams.editRole', { role: role.label }) : t('teams.newRole')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave(draft)
        }}
      >
        <Stack gap="sm">
          <TextInput label={t('teams.roleName')} value={draft.label} required maxLength={40}
            onChange={(e) => {
              const label = e.currentTarget.value
              // The ID follows the name until the role exists; after that it stays.
              setDraft((d) => ({ ...d, label, id: role ? d.id : label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) }))
            }}
          />
          <TextInput label={t('teams.roleDescription')} value={draft.description} maxLength={200}
            onChange={(e) => {
              const description = e.currentTarget.value
              setDraft((d) => ({ ...d, description }))
            }}
          />
          <Text size="sm" fw={600}>
            {t('teams.permissions')}
          </Text>
          {permissions.map((p) => (
            <Checkbox key={p.id} label={t(`teams.permission.${p.id.replace('.', '_')}`, { defaultValue: p.label })} description={p.id}
              checked={draft.permissions.includes(p.id)} onChange={(e) => toggle(p.id, e.currentTarget.checked)} />
          ))}
          {error && (
            <Text c="var(--color-down)" size="sm" role="alert">
              {error}
            </Text>
          )}
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={busy} disabled={!draft.id}>
              {t('teams.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
