import { Alert, Badge, Button, Group, MultiSelect, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { FirewallRange } from '@/api/types'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { SaveBar } from '@/pages/settings/editor'
import type { SwitchScope } from './scope'

/** A range's plan: network, name, firewalls in order, fallback and the switches it is for. A new
 *  one saves with Add; an existing one through the save bar, on its own inventory page (#1312).
 *  An imported range only takes its switches here: the rest comes from NetBox. */
export function RangeForm({ range, names, scope, onSaved, cidr, name }: {
  range: FirewallRange | null; names: string[]; scope: SwitchScope; onSaved?: (r: FirewallRange) => void
  /** A new plan for a prefix the inventory has already (its page): its network and name to start from. */
  cidr?: string; name?: string
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const imported = range?.source === 'import'
  const start = () => ({
    cidr: range?.cidr ?? cidr ?? '', name: range?.name ?? (name && name !== cidr ? name : ''), firewalls: range?.firewalls ?? [] as string[],
    fallback: range?.fallback ?? [] as string[], switches: range?.switches ?? [] as string[],
  })
  const [form, setForm] = useState(start)
  const was = start()
  const count = range ? (Object.keys(was) as (keyof typeof was)[]).filter((k) => JSON.stringify(was[k]) !== JSON.stringify(form[k])).length : 0
  useLeaveWarning(count > 0)
  const body = { cidr: form.cidr, name: form.name, switches: form.switches, firewalls: form.firewalls,
    fallback: form.fallback.filter((n) => !form.firewalls.includes(n)) }
  const save = useMutation({
    mutationFn: () => (range ? put<FirewallRange>(`/api/firewalls/ranges/${range.id}`, imported ? { switches: form.switches } : body)
      : post<FirewallRange>('/api/firewalls/ranges', body)),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: qk.firewalls })
      void qc.invalidateQueries({ queryKey: qk.inventoryAll })
      onSaved?.(r)
    },
  })
  const bad = !form.cidr.trim() || form.firewalls.length === 0
  return (
    <Stack gap="sm">
      {imported && <Badge variant="light" color="gray" w="fit-content">{t('firewalls.fromPlugin', { plugin: range?.plugin || 'NetBox' })}</Badge>}
      <TextInput label={t('firewalls.range')} placeholder={t('firewalls.rangePlaceholder')} value={form.cidr} disabled={imported}
        onChange={(e) => setForm({ ...form, cidr: e.currentTarget.value })} />
      <TextInput label={t('firewalls.name')} placeholder={t('firewalls.namePlaceholder')} value={form.name} disabled={imported}
        onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
      <MultiSelect label={t('firewalls.line')} description={t('firewalls.lineHelp')} data={names} value={form.firewalls}
        onChange={(v) => setForm({ ...form, firewalls: v })} searchable disabled={imported} />
      {form.firewalls.length > 1 && <Text size="xs" c="dimmed">{t('firewalls.cutInto', { count: form.firewalls.length })}</Text>}
      <MultiSelect label={t('firewalls.fallback')} description={t('firewalls.fallbackHelp')}
        data={names.filter((n) => !form.firewalls.includes(n))} value={form.fallback}
        onChange={(v) => setForm({ ...form, fallback: v })} searchable clearable disabled={imported} />
      <MultiSelect label={t('firewalls.switches')} description={t('firewalls.switchesHelp')}
        data={scope.options} value={form.switches}
        onChange={(v) => setForm({ ...form, switches: v })} searchable clearable />
      {imported && <Text size="xs" c="dimmed">{t('firewalls.fromPluginHelp', { plugin: range?.plugin || 'NetBox' })}</Text>}
      {range ? (
        <SaveBar count={count} bad={bad} saving={save.isPending} error={save.error} onSave={() => save.mutate()}
          onDiscard={() => setForm(start())} />
      ) : (
        <>
          {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
          <Group justify="flex-end">
            <Button loading={save.isPending} disabled={bad} onClick={() => save.mutate()}>{t('firewalls.save')}</Button>
          </Group>
        </>
      )}
    </Stack>
  )
}
