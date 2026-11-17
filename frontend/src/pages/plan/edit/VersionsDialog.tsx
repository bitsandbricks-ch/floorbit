import { Anchor, Button, Checkbox, Group, Modal, Paper, Stack, Text, TextInput } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconDeviceFloppy, IconRestore } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { ApplyResult, LayoutTemplate } from '@/api/types'
import { dateTime } from '@/lib/time'

/** Named versions of one hall's plan, kept in the template library (floorbit/layout_templates.py):
 *  save the hall as it is now, or put a saved one back, keeping the plan as it was first unless
 *  told not to. */
export function VersionsDialog({ opened, hall, hallName, onClose, onRestored }: {
  opened: boolean; hall: string; hallName: string; onClose: () => void; onRestored: () => Promise<unknown>
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const list = useQuery({ queryKey: qk.templates, queryFn: () => get<{ templates: LayoutTemplate[] }>('/api/templates').then((d) => d.templates), enabled: opened })
  const [name, setName] = useState('')
  const [keep, setKeep] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [asking, setAsking] = useState<LayoutTemplate | null>(null)
  const fail = (err: unknown) => notifications.show({ color: 'down', title: t('plan.edit.failed'), message: err instanceof Error ? err.message : String(err) })
  const stamp = () => `${hallName} · ${dateTime(new Date())}`
  // Versions of one hall: a template of the whole plan goes in through the template library.
  const versions = (list.data ?? []).filter((v) => v.versions.at(-1)?.halls === 1).sort((a, b) => b.updated.localeCompare(a.updated))
  const save = async (label: string) => {
    await post('/api/templates', { name: label, hall })
    await qc.invalidateQueries({ queryKey: qk.templates })
  }
  const saveNow = async () => {
    setBusy('save')
    try {
      const label = name.trim() || stamp()
      await save(label)
      setName('')
      notifications.show({ color: 'up', message: t('plan.edit.versions.saved', { name: label }) })
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }
  const restore = async (v: LayoutTemplate) => {
    setAsking(null)
    setBusy(v.id)
    try {
      if (keep) await save(t('plan.edit.versions.before', { name: v.name, when: dateTime(new Date()) }))
      await post<ApplyResult>(`/api/templates/${encodeURIComponent(v.id)}/apply`, { hall })
      await onRestored()
      notifications.show({ color: 'up', message: t('plan.edit.versions.restored', { name: v.name }) })
    } catch (err) {
      fail(err)
    } finally {
      setBusy(null)
    }
  }
  return (
    <Modal opened={opened} onClose={onClose} title={t('plan.edit.versions.title', { hall: hallName })} size="lg">
      <Stack gap="md">
        <Group align="flex-end" gap="xs" wrap="nowrap">
          <TextInput style={{ flex: 1 }} label={t('plan.edit.versions.name')} placeholder={stamp()} maxLength={80} value={name}
            onChange={(e) => setName(e.currentTarget.value)} onKeyDown={(e) => { if (e.key === 'Enter') void saveNow() }} />
          <Button leftSection={<IconDeviceFloppy size={16} />} loading={busy === 'save'} onClick={() => void saveNow()}>{t('plan.edit.versions.save')}</Button>
        </Group>
        <Checkbox checked={keep} onChange={(e) => setKeep(e.currentTarget.checked)} label={t('plan.edit.versions.keep')} />
        {!versions.length && !list.isPending && <Text size="sm" c="dimmed">{t('plan.edit.versions.none')}</Text>}
        <Stack gap="xs" role="list" aria-label={t('plan.edit.versions.list')}>
          {versions.map((v) => {
            const last = v.versions.at(-1)!
            return (
              <Paper key={v.id} withBorder p="sm" role="listitem">
                <Group justify="space-between" wrap="nowrap">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={600} truncate>{v.name}</Text>
                    <Text size="xs" c="dimmed">{t('plan.edit.versions.meta', { when: dateTime(new Date(last.saved)), blocks: last.seat_blocks, switches: last.switches })}</Text>
                  </div>
                  {asking?.id === v.id ? (
                    <Group gap={4} wrap="nowrap">
                      <Button size="xs" color="down" onClick={() => void restore(v)}>{t('plan.edit.versions.confirm')}</Button>
                      <Button size="xs" variant="default" onClick={() => setAsking(null)}>{t('plan.edit.versions.cancel')}</Button>
                    </Group>
                  ) : (
                    <Button size="xs" variant="default" leftSection={<IconRestore size={14} />} loading={busy === v.id} onClick={() => setAsking(v)}>
                      {t('plan.edit.versions.restore')}
                    </Button>
                  )}
                </Group>
              </Paper>
            )
          })}
        </Stack>
        <Text size="xs" c="dimmed">{t('plan.edit.versions.help')} <Anchor href="/templates" size="xs">{t('plan.edit.versions.library')}</Anchor></Text>
      </Stack>
    </Modal>
  )
}
