import { Alert, Button, Group, Modal, SegmentedControl, Select, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { EntitySelect } from '@/components/EntitySelect'
import type { IncidentBoard } from '@/api/types'
import { incidentTitle } from '@/lib/incidentTitle'

export interface IncidentDraft {
  seat?: string
  switch_id?: string
  title: string
  team: string | null
  note: string
}

/** File an incident for a seat or a switch. */
export function NewIncident({
  board,
  switches,
  opened,
  busy,
  error,
  onClose,
  onSave,
}: {
  board: IncidentBoard
  switches: { id: string; name: string }[]
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (draft: IncidentDraft) => void
}) {
  const { t } = useTranslation()
  const teams = board.teams.filter((x) => board.can_assign_any || board.workable_teams.includes(x.id))
  const [kind, setKind] = useState<'seat' | 'switch'>('seat')
  const [seat, setSeat] = useState('')
  const [switchId, setSwitchId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [team, setTeam] = useState<string | null>(teams[0]?.id ?? null)
  const [note, setNote] = useState('')
  // Two techs filing the same broken seat is the usual duplicate (issue #328): say so before saving.
  const seatKey = seat.trim().toLowerCase()
  const already = board.incidents.filter((i) => i.status !== 'fixed' && (kind === 'seat'
    ? !!seatKey && (i.seat ?? '').toLowerCase() === seatKey
    : !!switchId && !i.seat && i.switch_id === switchId))

  return (
    <Modal opened={opened} onClose={onClose} title={t('incidents.new')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave({ ...(kind === 'seat' ? { seat: seat.trim() } : { switch_id: switchId ?? '' }), title, team, note })
        }}
      >
        <Stack gap="sm">
          <SegmentedControl value={kind} onChange={(v) => setKind(v as 'seat' | 'switch')}
            data={[{ value: 'seat', label: t('incidents.atSeat') }, { value: 'switch', label: t('incidents.atSwitch') }]} />
          {kind === 'seat' ? (
            <EntitySelect kind="seats" label={t('incidents.seatNumber')} value={seat} required onChange={setSeat} />
          ) : (
            <Select label={t('incidents.whichSwitch')} data={switches.map((s) => ({ value: s.id, label: s.name }))} value={switchId}
              onChange={setSwitchId} searchable required />
          )}
          {already.length > 0 && (
            <Alert color="warn" variant="light" title={t('incidents.alreadyOpen', { count: already.length })}>
              {already.map((i) => (
                <Text key={i.id} size="sm">{incidentTitle(i.title, t)} · {t(`incidents.status.${i.status}`)}{i.assignee ? ` · ${i.assignee}` : ''}</Text>
              ))}
            </Alert>
          )}
          <TextInput label={t('incidents.what')} value={title} required maxLength={120} onChange={(e) => setTitle(e.currentTarget.value)} />
          <Select label={t('incidents.team')} data={teams.map((x) => ({ value: x.id, label: `${'· '.repeat(x.depth)}${x.name}` }))}
            value={team} onChange={setTeam} clearable={board.can_assign_any} />
          <Textarea label={t('incidents.note')} value={note} maxLength={2000} autosize minRows={2} onChange={(e) => setNote(e.currentTarget.value)} />
          {error && (
            <Text c="var(--color-down)" size="sm" role="alert">
              {error}
            </Text>
          )}
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={busy}>
              {t('incidents.file')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
