import { Alert, Button, Group, Stack, Text, Textarea, Title } from '@mantine/core'
import { IconNote } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { put } from '@/api/client'
import { qk } from '@/api/keys'
import type { SeatNote } from '@/api/types'

export const MAX_NOTE = 500

/** The crew's note on a seat (issue #180): "cable swapped at 14:20", so the next tech knows. */
export function SeatNoteBox({ seat, note }: { seat: string; note: SeatNote | null | undefined }) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const save = useMutation({
    mutationFn: (value: string) => put<{ note: SeatNote | null }>(`/api/plan/seats/${encodeURIComponent(seat)}/note`, { text: value }),
    onSuccess: () => {
      setEditing(false)
      void qc.invalidateQueries({ queryKey: qk.planAll })
    },
  })
  const when = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  const start = () => { setText(note?.text ?? ''); save.reset(); setEditing(true) }

  if (editing) {
    return (
      <Stack gap={6}>
        <Textarea label={t('plan.note.title')} description={t('plan.note.hint')} value={text} maxLength={MAX_NOTE} autosize minRows={2} maxRows={6}
          data-autofocus autoFocus onChange={(e) => setText(e.currentTarget.value)} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group gap="xs">
          <Button size="xs" onClick={() => save.mutate(text)} loading={save.isPending}>{t('plan.note.save')}</Button>
          <Button size="xs" variant="default" onClick={() => setEditing(false)}>{t('plan.note.cancel')}</Button>
          <Text size="xs" c="dimmed" ml="auto">{text.length} / {MAX_NOTE}</Text>
        </Group>
      </Stack>
    )
  }
  if (!note) {
    return <Group><Button size="xs" variant="default" leftSection={<IconNote size={14} />} onClick={start}>{t('plan.note.add')}</Button></Group>
  }
  return (
    <Stack gap={4} className="fb-seat-note">
      <Title order={3} size="h5">{t('plan.note.title')}</Title>
      <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{note.text}</Text>
      <Text size="xs" c="dimmed">{note.by ? t('plan.note.byAt', { by: note.by, time: when(note.at) }) : when(note.at)}</Text>
      <Group gap="xs">
        <Button size="compact-xs" variant="subtle" onClick={start}>{t('plan.note.edit')}</Button>
        <Button size="compact-xs" variant="subtle" color="down" onClick={() => save.mutate('')} loading={save.isPending}>{t('plan.note.remove')}</Button>
      </Group>
      {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
    </Stack>
  )
}
