import { Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SeatRow } from '@/api/types'

type Field = 'ip' | 'mac' | 'nick' | 'note'
export type SeatDraft = Record<Field | 'seat', string>

export function SeatForm({
  row,
  label,
  opened,
  busy,
  error,
  onClose,
  onSave,
}: {
  row: SeatRow | null
  label: (source: string) => string
  opened: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (draft: SeatDraft) => void
}) {
  const { t } = useTranslation()
  const m = row?.manual
  const [draft, setDraft] = useState<SeatDraft>({
    seat: row?.seat ?? '',
    ip: m?.ip ?? '',
    mac: m?.mac ?? '',
    nick: m?.nick ?? '',
    note: m?.note ?? '',
  })
  const set = (f: keyof SeatDraft) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.currentTarget.value
    setDraft((d) => ({ ...d, [f]: value }))
  }

  // What the other sources say, so it's clear what an empty field falls back to.
  function fallback(f: Field) {
    if (!row || f === 'note') return undefined
    const source = row.from[f]
    if (!source || source === 'manual' || !row[f]) return undefined
    return t('seatmap.fromSource', { value: row[f], source: label(source) })
  }

  const mono = { input: { fontFamily: 'var(--font-mono)' } }
  return (
    <Modal opened={opened} onClose={onClose} title={row ? t('seatmap.edit', { seat: row.seat }) : t('seatmap.newEntry')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave(draft)
        }}
      >
        <Stack gap="sm">
          {!row && <TextInput label={t('seatmap.seat')} value={draft.seat} onChange={set('seat')} required maxLength={16} placeholder="A-12" />}
          <TextInput label={t('seatmap.ip')} value={draft.ip} onChange={set('ip')} description={fallback('ip')} styles={mono} placeholder="192.0.2.10" maxLength={45} />
          <TextInput label={t('seatmap.mac')} value={draft.mac} onChange={set('mac')} description={fallback('mac')} styles={mono} placeholder="aa:bb:cc:dd:ee:ff" maxLength={20} />
          <TextInput label={t('seatmap.nick')} value={draft.nick} onChange={set('nick')} description={fallback('nick')} maxLength={64} />
          <TextInput label={t('seatmap.note')} value={draft.note} onChange={set('note')} maxLength={200} />
          {error && (
            <Text className="fb-tone-err" role="alert">
              ✕ {error}
            </Text>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={busy}>
              {t('seatmap.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
