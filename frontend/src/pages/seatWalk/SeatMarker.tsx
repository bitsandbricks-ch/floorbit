import { Badge, Button, Group, Menu, Stack, Text, TextInput } from '@mantine/core'
import { IconFlag } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, put } from '@/api/client'
import type { SeatMark, SeatMarkKind } from '@/api/seatWalk'

const KINDS: SeatMarkKind[] = ['broken', 'later', 'skip']

/** Mark the seat in front of you (issue #1356): broken socket, come back later, or nothing to walk,
 *  with a note. A walk skips marked seats; the mark shows on the strip and the row list. */
export function SeatMarker({ seat, mark, onMarked, onChanged }: {
  seat: string; mark?: SeatMark | null; onMarked: () => void; onChanged: () => void
}) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<SeatMarkKind | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const url = `/api/seat-walk/marks/${encodeURIComponent(seat)}`
  const save = async () => {
    setBusy(true); setError(null)
    try {
      await put(url, { mark: kind, note })
      setKind(null); setNote('')
      onChanged(); onMarked()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const unmark = async () => {
    setBusy(true)
    await del(url).catch(() => undefined)
    setBusy(false)
    onChanged()
  }
  if (kind) {
    return (
      <Stack gap="xs">
        <Text size="sm" fw={600}>{t(`seatWalkRows.markAs.${kind}`)}</Text>
        <TextInput size="sm" label={t('seatWalkRows.note')} placeholder={t('seatWalkRows.notePlaceholder')} maxLength={300}
          value={note} onChange={(e) => setNote(e.currentTarget.value)} data-autofocus
          onKeyDown={(e) => { if (e.key === 'Enter') void save() }} error={error} />
        <Group gap="xs">
          <Button size="compact-sm" loading={busy} onClick={() => void save()}>{t('seatWalkRows.saveMark')}</Button>
          <Button size="compact-sm" variant="default" onClick={() => setKind(null)}>{t('seatWalkRows.cancelMark')}</Button>
        </Group>
      </Stack>
    )
  }
  return (
    <Group gap="xs">
      {mark && (
        <>
          <Badge variant="light" color="warn" tt="none">{t(`seatWalkRows.markAs.${mark.mark}`)}</Badge>
          <Text size="sm" c="dimmed">
            {t('seatWalkRows.markedBy', { mark: t(`seatWalkRows.markShort.${mark.mark}`), by: mark.by })}
            {mark.note ? `: ${mark.note}` : ''}</Text>
          <Button size="compact-xs" variant="subtle" loading={busy} onClick={() => void unmark()}>{t('seatWalkRows.unmark')}</Button>
        </>
      )}
      {!mark && (
        <Menu position="bottom-start" withinPortal>
          <Menu.Target>
            <Button size="compact-sm" variant="default" leftSection={<IconFlag size={14} />}>{t('seatWalkRows.mark')}</Button>
          </Menu.Target>
          <Menu.Dropdown>
            {KINDS.map((k) => <Menu.Item key={k} onClick={() => setKind(k)}>{t(`seatWalkRows.markAs.${k}`)}</Menu.Item>)}
          </Menu.Dropdown>
        </Menu>
      )}
    </Group>
  )
}
