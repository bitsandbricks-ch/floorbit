import { ActionIcon, Button, Code, Group, Modal, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { OidcList, OidcProvider, RoleMappingRule } from '@/api/types'

export interface ProviderDraft {
  id: string
  name: string
  issuer: string
  client_id: string
  scopes: string
  role_claim: string
  role_mapping: RoleMappingRule[]
}

/** Add or change an OIDC provider. The client secret is never entered here: it lives on the server. */
export function ProviderForm({
  provider,
  list,
  opened,
  busy,
  error,
  onClose,
  onSave,
}: {
  provider: OidcProvider | null
  list: OidcList
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (draft: ProviderDraft) => void
}) {
  const { t } = useTranslation()
  const [d, setD] = useState<ProviderDraft>({
    id: provider?.id ?? '',
    name: provider?.name ?? '',
    issuer: provider?.issuer ?? '',
    client_id: provider?.client_id ?? '',
    scopes: provider?.scopes ?? 'openid profile email',
    role_claim: provider?.role_claim ?? 'groups',
    role_mapping: provider?.role_mapping ?? [],
  })
  const set = (patch: Partial<ProviderDraft>) => setD((x) => ({ ...x, ...patch }))
  const setRule = (i: number, patch: Partial<RoleMappingRule>) =>
    set({ role_mapping: d.role_mapping.map((r, j) => (j === i ? { ...r, ...patch } : r)) })
  const roleOptions = list.roles.map((r) => ({ value: r.id, label: r.label }))
  const secretEnv = provider?.secret_env ?? (d.id ? `OIDC_${d.id.toUpperCase()}_CLIENT_SECRET` : 'OIDC_<ID>_CLIENT_SECRET')
  const callback = provider?.callback_url ?? list.callback_template.replace(/ID\/callback$/, `${d.id || '<id>'}/callback`)

  return (
    <Modal size="lg" opened={opened} onClose={onClose} title={provider ? t('signin.editProvider', { name: provider.name }) : t('signin.newProvider')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave({ ...d, role_mapping: d.role_mapping.filter((r) => r.value.trim()) })
        }}
      >
        <Stack gap="sm">
          <TextInput label={t('signin.name')} description={t('signin.nameHint')} value={d.name} required maxLength={40}
            onChange={(e) => {
              const name = e.currentTarget.value
              // The ID follows the name until the provider exists; it is part of its URLs after that.
              set({ name, ...(provider ? {} : { id: name.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 24) }) })
            }}
          />
          <TextInput label={t('signin.issuer')} description={t('signin.issuerHint')} value={d.issuer} required
            placeholder="https://auth.example.com/application/o/floorbit/" onChange={(e) => set({ issuer: e.currentTarget.value })} />
          <TextInput label={t('signin.clientId')} value={d.client_id} required onChange={(e) => set({ client_id: e.currentTarget.value })} />
          <div>
            <Text size="sm" fw={500}>{t('signin.secret')}</Text>
            <Text size="xs" c="dimmed">{t('signin.secretHint')}</Text>
            <Code>{secretEnv}</Code>
          </div>
          <div>
            <Text size="sm" fw={500}>{t('signin.callback')}</Text>
            <Text size="xs" c="dimmed">{t('signin.callbackHint')}</Text>
            <Code>{callback}</Code>
          </div>
          <TextInput label={t('signin.scopes')} value={d.scopes} onChange={(e) => set({ scopes: e.currentTarget.value })} />
          <TextInput label={t('signin.claim')} description={t('signin.claimHint')} value={d.role_claim}
            onChange={(e) => set({ role_claim: e.currentTarget.value })} />
          <Text size="sm" fw={500}>{t('signin.mapping')}</Text>
          <Text size="xs" c="dimmed" mt={-8}>{t('signin.mappingHint')}</Text>
          {d.role_mapping.map((r, i) => (
            <Group key={i} gap="xs" wrap="nowrap">
              <TextInput style={{ flex: 1 }} aria-label={t('signin.claimValue')} placeholder={t('signin.claimValue')} value={r.value}
                onChange={(e) => setRule(i, { value: e.currentTarget.value })} />
              <Select w={160} aria-label={t('signin.role')} data={roleOptions} value={r.role} allowDeselect={false}
                onChange={(v) => v && setRule(i, { role: v })} />
              <ActionIcon variant="subtle" color="down" aria-label={t('signin.removeRule')}
                onClick={() => set({ role_mapping: d.role_mapping.filter((_, j) => j !== i) })}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
          <Button variant="default" size="xs" leftSection={<IconPlus size={14} />} w="fit-content"
            onClick={() => set({ role_mapping: [...d.role_mapping, { value: '', role: 'viewer' }] })}>
            {t('signin.addRule')}
          </Button>
          {error && (
            <Text c="var(--color-down)" size="sm" role="alert">
              {error}
            </Text>
          )}
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={busy} disabled={!d.id}>
              {t('signin.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
