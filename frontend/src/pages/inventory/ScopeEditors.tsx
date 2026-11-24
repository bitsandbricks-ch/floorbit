import { ActionIcon, Badge, Button, ColorInput, Group, MultiSelect, PasswordInput, SegmentedControl, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { CredentialInfo, FeatureInfo, InventoryOverview, InventoryTag, Origin } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { DEVICE_ICONS, DeviceIcon } from './icons'
import { useCustomIcons } from './scope'

/** Where an inherited value comes from, in words ("from group Hall A"). */
export function FromLabel({ from }: { from: Origin | null | undefined }) {
  const { t } = useTranslation()
  if (!from) return <Text span size="xs" c="dimmed">{t('inventory.scope.default')}</Text>
  if (from.type === 'device') return <Text span size="xs" c="dimmed">{t('inventory.scope.fromDevice')}</Text>
  return (
    <Text span size="xs" c="dimmed">
      {t(`inventory.scope.from.${from.type}`, {
        name: from.type === 'defaults' ? t('inventory.groups.all')
          : from.type === 'type' ? t(`inventory.types.name.${from.id}`, { defaultValue: from.name }) : from.name,
      })}
    </Text>
  )
}

const SWATCHES = ['#1e88e5', '#00acc1', '#43a047', '#7cb342', '#fdd835', '#fb8c00', '#e53935', '#8e24aa', '#6d4c41', '#546e7a']

/** Icon and colour pickers. Empty = inherit (or the role's own). */
export function LookFields({ icon, color, icons, onIcon, onColor, inherited }: {
  icon: string; color: string; icons: string[]; onIcon: (v: string) => void; onColor: (v: string) => void
  inherited?: { icon: string; color: string }
}) {
  const { t } = useTranslation()
  const uploaded = useCustomIcons().data?.icons ?? []
  const label = (i: string) => uploaded.find((u) => u.id === i)?.name ?? t(`inventory.icon.${i}`, { defaultValue: i })
  const data = [
    { group: t('inventory.look.builtIn'), items: icons.map((i) => ({ value: i, label: label(i) })) },
    ...(uploaded.length ? [{ group: t('inventory.look.uploaded'), items: uploaded.map((u) => ({ value: u.id, label: u.name })) }] : []),
  ]
  return (
    <Group grow align="flex-start">
      <Select
        label={t('inventory.look.icon')}
        placeholder={inherited?.icon ? t('inventory.look.inherits', { value: label(inherited.icon) }) : t('inventory.look.roleIcon')}
        data={data}
        value={icon || null}
        onChange={(v) => onIcon(v ?? '')}
        clearable
        searchable
        leftSection={icon && (DEVICE_ICONS[icon] || uploaded.some((u) => u.id === icon)) ? <DeviceIcon icon={icon} color={color} size={20} /> : undefined}
        renderOption={({ option }) => (
          <Group gap="xs" wrap="nowrap">
            <DeviceIcon icon={option.value} size={20} />
            <Text size="sm">{option.label}</Text>
          </Group>
        )}
      />
      <ColorInput
        label={t('inventory.look.color')}
        placeholder={inherited?.color || t('inventory.look.noColor')}
        format="hex"
        swatches={SWATCHES}
        swatchesPerRow={10}
        value={color}
        onChange={onColor}
        eyeDropperButtonProps={{ 'aria-label': t('inventory.look.pickColor') }}
      />
    </Group>
  )
}

/** Tags picked from the list there is (never typed). */
export function TagPicker({ tags, value, onChange, label }: { tags: InventoryTag[]; value: string[]; onChange: (v: string[]) => void; label?: string }) {
  const { t } = useTranslation()
  return (
    <MultiSelect
      label={label ?? t('inventory.tags.label')}
      placeholder={tags.length ? t('inventory.tags.pick') : t('inventory.tags.none')}
      data={tags.map((tag) => ({ value: tag.id, label: tag.name }))}
      value={value}
      onChange={onChange}
      searchable
      clearable
      disabled={!tags.length}
    />
  )
}

/** Name and value pairs. Inherited ones are shown (read-only) under the own ones. */
export function PropertiesEditor({ value, inherited, busy, canEdit, onSave }: {
  value: Record<string, string>
  inherited?: Record<string, { value: string; from: Origin }>
  busy: boolean
  canEdit: boolean
  onSave: (props: Record<string, string>) => void
}) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(value))
  const dirty = JSON.stringify(rows) !== JSON.stringify(Object.entries(value))
  const others = Object.entries(inherited ?? {}).filter(([, v]) => v.from.type !== 'device')
  return (
    <Stack gap="xs">
      {rows.length === 0 && <Text size="sm" c="dimmed">{t('inventory.props.none')}</Text>}
      {rows.map(([k, v], i) => (
        <Group key={i} gap="xs" wrap="nowrap" align="flex-end">
          <TextInput aria-label={t('inventory.props.name')} placeholder="rack" value={k} disabled={!canEdit} style={{ flex: '0 0 40%' }}
            styles={{ input: { fontFamily: 'var(--font-mono)' } }}
            onChange={(e) => { const name = e.currentTarget.value; setRows((r) => r.map((row, j) => (j === i ? [name, row[1]] : row))) }} />
          <TextInput aria-label={t('inventory.props.value')} value={v} disabled={!canEdit} style={{ flex: 1 }}
            onChange={(e) => { const val = e.currentTarget.value; setRows((r) => r.map((row, j) => (j === i ? [row[0], val] : row))) }} />
          {canEdit && (
            <ActionIcon variant="subtle" color="gray" mb={4} aria-label={t('inventory.props.remove', { name: k })}
              onClick={() => setRows((r) => r.filter((_, j) => j !== i))}>
              <IconTrash size={16} />
            </ActionIcon>
          )}
        </Group>
      ))}
      {canEdit && (
        <Group justify="space-between">
          <Button size="xs" variant="subtle" leftSection={<IconPlus size={14} />} onClick={() => setRows((r) => [...r, ['', '']])}>
            {t('inventory.props.add')}
          </Button>
          <Button size="xs" disabled={!dirty} loading={busy}
            onClick={() => onSave(Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim().toLowerCase(), v])))}>
            {t('inventory.save')}
          </Button>
        </Group>
      )}
      {others.length > 0 && (
        <Table fz="sm" verticalSpacing={4}>
          <Table.Tbody>
            {others.map(([k, v]) => (
              <Table.Tr key={k} style={{ opacity: k in Object.fromEntries(rows) ? 0.5 : 1 }}>
                <Table.Td ff="monospace">{k}</Table.Td>
                <Table.Td>{v.value}</Table.Td>
                <Table.Td ta="right"><FromLabel from={v.from} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  )
}

type Choice = 'inherit' | 'on' | 'off'

/** Feature switches: inherit, on or off, each with what it is now and why. */
export function FeaturesEditor({ catalog, value, resolved, busy, canEdit, onSave }: {
  catalog: FeatureInfo[]
  value: Record<string, boolean>
  resolved?: Record<string, { on: boolean; from: Origin | null }>
  busy: boolean
  canEdit: boolean
  onSave: (features: Record<string, boolean | null>) => void
}) {
  const { t } = useTranslation()
  const choice = (id: string): Choice => (id in value ? (value[id] ? 'on' : 'off') : 'inherit')
  const section = (core: boolean) => catalog.filter((f) => f.core === core)
  const row = (f: FeatureInfo) => {
    const now = resolved?.[f.id]
    return (
      <Table.Tr key={f.id}>
        <Table.Td>
          <Text size="sm" fw={500}>{f.core ? t(`inventory.feature.${f.id}`) : f.name}</Text>
          {now ? (
            <Text size="xs" c="dimmed">
              {now.on ? t('inventory.features.isOn') : t('inventory.features.isOff')} · <FromLabel from={now.from} />
            </Text>
          ) : (
            <Text size="xs" c="dimmed">{f.default ? t('inventory.features.defaultOn') : t('inventory.features.defaultOff')}</Text>
          )}
        </Table.Td>
        <Table.Td ta="right">
          <SegmentedControl size="xs" disabled={!canEdit || busy} value={choice(f.id)}
            aria-label={f.core ? t(`inventory.feature.${f.id}`) : f.name}
            data={[{ value: 'inherit', label: t('inventory.features.inherit') }, { value: 'on', label: t('inventory.features.on') },
              { value: 'off', label: t('inventory.features.off') }]}
            onChange={(v) => onSave({ ...value, [f.id]: v === 'inherit' ? null : v === 'on' })} />
        </Table.Td>
      </Table.Tr>
    )
  }
  return (
    <Stack gap="xs">
      <Text size="xs" fw={600} c="dimmed" tt="uppercase">{t('inventory.features.core')}</Text>
      <Table verticalSpacing={6}><Table.Tbody>{section(true).map(row)}</Table.Tbody></Table>
      <Text size="xs" fw={600} c="dimmed" tt="uppercase">{t('inventory.features.plugins')}</Text>
      <Text size="xs" c="dimmed">{t('inventory.features.pluginsHint')}</Text>
      <Table verticalSpacing={6}><Table.Tbody>{section(false).map(row)}</Table.Tbody></Table>
    </Stack>
  )
}

export interface CredentialDraft {
  kind: string
  username: string
  secret: string
  priv_secret: string
  auth_protocol: string
  priv_protocol: string
}

/** Credentials set right here (write-only), and a form to set or replace one. */
export function CredentialsEditor({ own, inherited, overview, canSet, busy, error, onSet, onRemove }: {
  own: CredentialInfo[]
  inherited?: Record<string, CredentialInfo & { from: Origin; blocked: boolean }>
  overview: InventoryOverview
  canSet: boolean
  busy: boolean
  error: string | null
  onSet: (draft: CredentialDraft) => Promise<unknown>
  onRemove: (cred: CredentialInfo) => void
}) {
  const { t } = useTranslation()
  const blank: CredentialDraft = { kind: 'ssh', username: '', secret: '', priv_secret: '', auth_protocol: 'SHA', priv_protocol: 'AES' }
  const [draft, setDraft] = useState<CredentialDraft | null>(null)
  const has = (kind: string) => own.find((c) => c.kind === kind)
  const set = (k: keyof CredentialDraft) => (v: string) => setDraft((d) => (d ? { ...d, [k]: v } : d))
  const replacing = draft ? has(draft.kind) : undefined
  const usesUser = draft && draft.kind !== 'snmp_v2c'
  // A trap user may be authNoPriv or noAuthNoPriv: both passphrases are optional.
  const trap = draft?.kind === 'snmp_trap'
  return (
    <Stack gap="xs">
      {Object.keys(inherited ?? {}).length > 0 && (
        <Table fz="sm" verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('inventory.creds.kind')}</Table.Th>
              <Table.Th>{t('inventory.creds.username')}</Table.Th>
              <Table.Th>{t('inventory.creds.usedFrom')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {Object.entries(inherited ?? {}).map(([kind, c]) => (
              <Table.Tr key={kind}>
                <Table.Td>{t(`inventory.creds.kinds.${kind}`)}</Table.Td>
                <Table.Td ff="monospace">{c.username || '–'}</Table.Td>
                <Table.Td>
                  <FromLabel from={c.from} />
                  {c.blocked && <Badge ml={6} size="xs" color="down" variant="light">{t('inventory.blocks.badge')}</Badge>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {own.length === 0 && !inherited && <Text size="sm" c="dimmed">{t('inventory.creds.noneHere')}</Text>}
      {own.map((c) => (
        <Group key={c.id} justify="space-between" wrap="nowrap">
          <div>
            <Text size="sm" fw={500}>{t(`inventory.creds.kinds.${c.kind}`)} {c.username && <Text span ff="monospace" size="sm">{c.username}</Text>}</Text>
            <Text size="xs" c="dimmed">{t('inventory.creds.setHere', { who: c.set_by ?? '?' })}</Text>
          </div>
          {canSet && (
            <Group gap={4} wrap="nowrap">
              <Button size="xs" variant="subtle" onClick={() => setDraft({ ...blank, kind: c.kind, username: c.username, auth_protocol: c.auth_protocol || 'SHA', priv_protocol: c.priv_protocol || 'AES' })}>
                {t('inventory.creds.replace')}
              </Button>
              <ConfirmButton size="xs" variant="subtle" danger label={t('inventory.creds.remove')}
                question={t('inventory.creds.removeQ', { kind: t(`inventory.creds.kinds.${c.kind}`) })} onConfirm={() => onRemove(c)} />
            </Group>
          )}
        </Group>
      ))}
      {canSet && !draft && (
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setDraft(blank)} style={{ alignSelf: 'flex-start' }}>
          {t('inventory.creds.add')}
        </Button>
      )}
      {!canSet && <Text size="xs" c="dimmed">{t('inventory.creds.adminsOnly')}</Text>}
      {draft && (
        <form onSubmit={(e) => { e.preventDefault(); onSet(draft).then(() => setDraft(null), () => undefined) }}>
          <Stack gap="xs" p="sm" style={{ border: '1px solid var(--ui-border, var(--mantine-color-default-border))', borderRadius: 8 }}>
            <Select label={t('inventory.creds.kind')} allowDeselect={false}
              data={overview.credential_kinds.map((k) => ({ value: k, label: t(`inventory.creds.kinds.${k}`) }))}
              value={draft.kind} onChange={(v) => set('kind')(v ?? 'ssh')} />
            {usesUser && (
              <TextInput label={t('inventory.creds.username')} value={draft.username} autoComplete="off"
                required={draft.kind !== 'api'} onChange={(e) => set('username')(e.currentTarget.value)} />
            )}
            <PasswordInput label={t(`inventory.creds.secretLabel.${draft.kind}`)} value={draft.secret} autoComplete="new-password"
              required={!replacing && !trap} placeholder={replacing ? t('inventory.creds.keep') : undefined}
              onChange={(e) => set('secret')(e.currentTarget.value)} />
            {(draft.kind === 'snmp_v3' || trap) && (
              <>
                <Group grow>
                  <Select label={t('inventory.creds.authProtocol')} allowDeselect={false} data={overview.auth_protocols}
                    value={draft.auth_protocol} onChange={(v) => set('auth_protocol')(v ?? 'SHA')} />
                  <Select label={t('inventory.creds.privProtocol')} allowDeselect={false} data={overview.priv_protocols}
                    value={draft.priv_protocol} onChange={(v) => set('priv_protocol')(v ?? 'AES')} />
                </Group>
                <PasswordInput label={trap ? t('inventory.creds.privSecretOptional') : t('inventory.creds.privSecret')} value={draft.priv_secret} autoComplete="new-password"
                  required={!replacing && !trap} placeholder={replacing ? t('inventory.creds.keep') : undefined}
                  onChange={(e) => set('priv_secret')(e.currentTarget.value)} />
              </>
            )}
            <Text size="xs" c="dimmed">{t('inventory.creds.writeOnly')}</Text>
            {error && <Text size="sm" className="fb-tone-err" role="alert">✕ {error}</Text>}
            <Group justify="flex-end">
              <Button size="xs" variant="default" onClick={() => setDraft(null)}>{t('common.cancel')}</Button>
              <Button size="xs" type="submit" loading={busy}>{t('inventory.creds.save')}</Button>
            </Group>
          </Stack>
        </form>
      )}
    </Stack>
  )
}
