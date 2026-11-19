import { Alert, Button, Group, Stack, Textarea } from '@mantine/core'
import { IconFlag } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { BouncePort } from '@/components/BouncePort'

/** What a tech can do from the seat inspector (issue #151): bounce the seat's port with their own
 *  switch login, and flag the seat for a tech. The same calls as the floor plan editor. */
export function SeatActions({ seat, hasPort }: { seat: string; hasPort: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canAct = useCan('ports.act')
  const canFlag = useCan('incidents.work')
  const [done, setDone] = useState<string | null>(null)
  const [flagging, setFlagging] = useState(false)
  const [note, setNote] = useState('')

  const flag = useMutation({
    // The same title as the editor's flag, whatever the language.
    mutationFn: () => post('/api/incidents', { seat, title: 'Tech visit', note: note.trim() }),
    onSuccess: () => {
      setFlagging(false)
      setNote('')
      setDone(t('plan.flagged', { seat }))
      void qc.invalidateQueries({ queryKey: qk.planAll })
    },
  })

  if (!(canAct && hasPort) && !canFlag) return null
  return (
    <Stack gap="xs">
      {done && <Alert color="up" withCloseButton onClose={() => setDone(null)}>{done}</Alert>}
      {flag.error && <Alert color="down" role="alert">{flag.error.message}</Alert>}
      {flagging ? (
        <Stack gap="xs">
          <Textarea label={t('plan.flagNote')} autosize minRows={2} maxLength={500} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          <Group gap="xs">
            <Button size="xs" loading={flag.isPending} onClick={() => flag.mutate()}>{t('plan.flagSend')}</Button>
            <Button size="xs" variant="default" onClick={() => setFlagging(false)}>{t('common.cancel')}</Button>
          </Group>
        </Stack>
      ) : (
        <Group gap="xs">
          {hasPort && <BouncePort seat={seat} onBounced={setDone} />}
          {canFlag && (
            <Button size="xs" variant="light" leftSection={<IconFlag size={14} />} onClick={() => setFlagging(true)}>{t('plan.flag')}</Button>
          )}
        </Group>
      )}
    </Stack>
  )
}
