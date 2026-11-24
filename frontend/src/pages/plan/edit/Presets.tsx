import { ActionIcon, Alert, Badge, Button, Group, Modal, Paper, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { toastDone } from '@/components/toast'
import type { Raw } from './clipboard'

/** A preset: items of the plan kept together (floorbit/plan_presets.py). */
export interface PlanPreset {
  id: string
  name: string
  saved: string
  counts: Partial<Record<Raw['kind'], number>>
  items: Raw[]
}

const KEY = ['plan-presets'] as const

/** Names the selection and keeps it as a preset. */
export function SavePresetDialog({ items, onClose }: { items: Raw[] | null; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const save = useMutation({
    mutationFn: () => post<PlanPreset>('/api/plan-presets', { name: name.trim(), items }),
    onSuccess: (p) => { toastDone(t('presets.saved', { name: p.name })); void qc.invalidateQueries({ queryKey: KEY }); setName(''); onClose() },
  })
  return (
    <Modal opened={!!items} onClose={onClose} title={t('presets.saveTitle')}>
      <Stack gap="sm">
        <TextInput label={t('presets.name')} value={name} maxLength={60} required data-autofocus
          onChange={(e) => setName(e.currentTarget.value)} onKeyDown={(e) => { if (e.key === 'Enter' && name.trim()) save.mutate() }} />
        <Text size="sm" c="dimmed">{t('presets.saveHelp', { count: items?.length ?? 0 })}</Text>
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('presets.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** The presets to place in this hall; placing one works like a paste. */
export function PresetsDialog({ opened, onClose, onPlace }: { opened: boolean; onClose: () => void; onPlace: (p: PlanPreset) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const list = useQuery({ queryKey: KEY, queryFn: () => get<{ presets: PlanPreset[] }>('/api/plan-presets').then((d) => d.presets), enabled: opened })
  const remove = useMutation({
    mutationFn: (p: PlanPreset) => del(`/api/plan-presets/${encodeURIComponent(p.id)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  })
  const presets = [...(list.data ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  return (
    <Modal opened={opened} onClose={onClose} title={t('presets.placeTitle')} size="lg">
      <Stack gap="sm">
        {!presets.length && !list.isPending && <Text size="sm" c="dimmed">{t('presets.none')}</Text>}
        <Stack gap="xs" role="list" aria-label={t('presets.list')}>
          {presets.map((p) => (
            <Paper key={p.id} withBorder p="sm" role="listitem">
              <Group justify="space-between" wrap="nowrap" gap="sm">
                <Stack gap={4} style={{ minWidth: 0 }}>
                  <Text fw={600} truncate>{p.name}</Text>
                  <Group gap={6}>
                    {Object.entries(p.counts).map(([kind, n]) => (
                      <Badge key={kind} size="sm" variant="light" color="gray">{t(`presets.kind.${kind}`, { count: n })}</Badge>
                    ))}
                  </Group>
                </Stack>
                <Group gap={6} wrap="nowrap">
                  <Button size="xs" variant="default" onClick={() => { onPlace(p); onClose() }} aria-label={t('presets.placeOne', { name: p.name })}>{t('presets.place')}</Button>
                  <Tooltip label={t('presets.delete')}>
                    <ActionIcon variant="subtle" color="down" aria-label={t('presets.deleteOne', { name: p.name })} loading={remove.isPending && remove.variables?.id === p.id}
                      onClick={() => remove.mutate(p)}><IconTrash size={16} /></ActionIcon>
                  </Tooltip>
                </Group>
              </Group>
            </Paper>
          ))}
        </Stack>
        {remove.error && <Alert color="down" role="alert">{remove.error.message}</Alert>}
        <Text size="xs" c="dimmed">{t('presets.help')}</Text>
      </Stack>
    </Modal>
  )
}
