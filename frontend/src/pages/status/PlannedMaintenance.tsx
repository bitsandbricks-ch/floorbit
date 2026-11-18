import { Badge, Button, Group, Paper, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconTrash } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmIcon } from '@/components/ConfirmButton'
import { DateTimeInput } from '@/components/DateTimeInput'
import { del, post } from '@/api/client'
import type { StatusPlanned } from '@/api/types'
import { fromLocal } from './time'
import { dayClock } from '@/lib/time'

/** Maintenance announced ahead on the public status page (issue #422). */
export function PlannedMaintenance({ planned, running, canSet, onChange }: {
  planned: StatusPlanned[]; running: string | null; canSet: boolean; onChange: () => void
}) {
  const { t, i18n } = useTranslation()
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [text, setText] = useState('')
  const [area, setArea] = useState('')
  const add = useMutation({
    mutationFn: () => post('/api/status-page/maintenance', { start: fromLocal(start), end: fromLocal(end), text, area }),
    onSuccess: () => { setStart(''); setEnd(''); setText(''); setArea(''); onChange() },
  })
  const cancel = useMutation({ mutationFn: (id: string) => del(`/api/status-page/maintenance/${id}`), onSuccess: onChange })
  const when = (at: number) => dayClock(at, i18n.language)
  const error = add.error || cancel.error
  return (
    <Paper withBorder radius="lg" p="md" data-testid="planned">
      <Title order={2} size="h5" mb={4}>{t('status.planned')}</Title>
      <Text size="sm" c="dimmed" mb="sm">{t('status.plannedIntro')}</Text>
      {canSet && (
        <Stack gap="xs" mb="md">
          <Group gap="xs" align="flex-end" wrap="wrap">
            <DateTimeInput label={t('status.plannedStart')} value={start} onChange={setStart} />
            <DateTimeInput label={t('status.plannedEnd')} value={end} onChange={setEnd} />
            <TextInput label={t('status.area')} placeholder={t('status.areaPlaceholder')} value={area} maxLength={80}
              onChange={(e) => setArea(e.currentTarget.value)} style={{ flex: 1, minWidth: 140 }} />
          </Group>
          <Group gap="xs" align="flex-end">
            <TextInput label={t('status.plannedText')} placeholder={t('status.plannedPlaceholder')} value={text} maxLength={500}
              onChange={(e) => setText(e.currentTarget.value)} style={{ flex: 1 }} />
            <Button disabled={!start || !end || !text.trim()} loading={add.isPending} onClick={() => add.mutate()}>
              {t('status.plannedAdd')}
            </Button>
          </Group>
          {error && <Text size="sm" c="down" role="alert">{error.message}</Text>}
        </Stack>
      )}
      {planned.length === 0 ? <Text size="sm" c="dimmed">{t('status.plannedNone')}</Text> : (
        <Stack gap="xs">
          {planned.map((m) => (
            <Group key={m.id} gap="sm" wrap="nowrap" align="flex-start" justify="space-between">
              <div style={{ minWidth: 0 }}>
                <Group gap={6}>
                  {m.id === running && <Badge color="warn" size="sm">{t('status.plannedNow')}</Badge>}
                  <Text size="xs" c="dimmed">{[`${when(m.start)} – ${when(m.end)}`, m.area].filter(Boolean).join(' · ')}</Text>
                </Group>
                <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{m.text}</Text>
              </div>
              {canSet && (
                <ConfirmIcon label={t('status.plannedCancel')} onConfirm={() => cancel.mutate(m.id)}>
                  <IconTrash size={16} />
                </ConfirmIcon>
              )}
            </Group>
          ))}
        </Stack>
      )}
    </Paper>
  )
}
