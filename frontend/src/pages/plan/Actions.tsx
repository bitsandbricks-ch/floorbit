import { Alert, Button, Group, Stack, Textarea } from '@mantine/core'
import { IconFlag, IconPlugConnected } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { PortDialog, type PortRequest } from '../security/PortDialog'

interface PortInfo { available: boolean; needs_login: boolean; plugin: string | null }

/** What a tech can do from the seat inspector (issue #151): bounce the seat's port with their own
 *  switch login, and flag the seat for a tech. The same calls as the floor plan editor. */
export function SeatActions({ seat, hasPort }: { seat: string; hasPort: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canAct = useCan('ports.act')
  const canFlag = useCan('incidents.work')
  const info = useQuery({ queryKey: qk.ports, queryFn: () => get<PortInfo>('/api/ports'), enabled: canAct })
  const [request, setRequest] = useState<PortRequest | null>(null)
  const [matchSeat, setMatchSeat] = useState<string | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [flagging, setFlagging] = useState(false)
  const [note, setNote] = useState('')

  const bounce = useMutation({
    mutationFn: (extra: Record<string, string | boolean | undefined>) => post<{ message: string }>('/api/ports/bounce', { seat, ...extra }),
    onSuccess: (r) => {
      setRequest(null)
      setMatchSeat(null)
      setDone(r.message)
    },
    onError: (e) => {
      // A match seat (issue #31): ask a second time instead of failing.
      const zone = e instanceof ApiError && typeof e.data.match_seat === 'string' ? e.data.match_seat : null
      setMatchSeat(zone)
      setDialogError(zone ? null : e.message)
    },
  })
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

  const mayBounce = canAct && hasPort && !!info.data?.available
  if (!mayBounce && !canFlag) return null
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
          {mayBounce && (
            <Button size="xs" color="warn" variant="light" leftSection={<IconPlugConnected size={14} />}
              onClick={() => { setDialogError(null); setRequest({ action: 'bounce', seat, where: t('plan.seat', { seat }) }) }}>
              {t('security.bounce')}
            </Button>
          )}
          {canFlag && (
            <Button size="xs" variant="light" leftSection={<IconFlag size={14} />} onClick={() => setFlagging(true)}>{t('plan.flag')}</Button>
          )}
        </Group>
      )}
      <PortDialog request={request} needsLogin={!!info.data?.needs_login} busy={bounce.isPending} error={dialogError} matchSeat={matchSeat}
        onClose={() => { setRequest(null); setMatchSeat(null) }}
        onConfirm={(extra) => bounce.mutate(extra)} />
    </Stack>
  )
}
