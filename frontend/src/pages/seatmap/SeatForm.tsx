import { Button, Fieldset, Group, Modal, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import type { FoundPort, SeatRow } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'

type Field = 'switch' | 'port' | 'ip' | 'mac' | 'nick' | 'note'
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
    switch: m?.switch ?? '',
    port: m?.port ?? '',
    ip: m?.ip ?? '',
    mac: m?.mac ?? '',
    nick: m?.nick ?? '',
    note: m?.note ?? '',
  })
  const [lookFor, setLookFor] = useState(m?.mac ?? '')
  const patch = (p: Partial<SeatDraft>) => setDraft((d) => ({ ...d, ...p }))
  const set = (f: keyof SeatDraft) => (e: React.ChangeEvent<HTMLInputElement>) => patch({ [f]: e.currentTarget.value })

  // The MAC only finds the port; the port is what gets saved, and it can be changed again.
  const find = useMutation({
    mutationFn: () => post<FoundPort>('/api/seat-map/find-port', { mac: lookFor, seat: draft.seat }),
    onSuccess: (f) => patch({ switch: f.switch, port: f.port }),
  })

  // What the other sources say, so it's clear what an empty field falls back to.
  function fallback(f: Field) {
    if (!row || f === 'note' || f === 'switch') return undefined
    const source = row.from[f]
    if (!source || source === 'manual' || !row[f]) return undefined
    if (f === 'port') {
      const origin = row.port_origin ? t(`seatmap.originLong.${row.port_origin}`).toLowerCase() : label(source)
      return t('seatmap.fromOrigin', { value: `${row.switch} ${row.port}`, origin })
    }
    return t('seatmap.fromSource', { value: row[f], source: label(source) })
  }

  const mono = { input: { fontFamily: 'var(--font-mono)' } }
  const found = find.data
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={row ? t('seatmap.edit', { seat: row.seat }) : t('seatmap.newEntry')}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSave(draft)
        }}
      >
        <Stack gap="sm">
          {!row && <EntitySelect kind="seats" label={t('seatmap.seat')} value={draft.seat} required onChange={(v) => patch({ seat: v })} />}
          <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
            <EntitySelect kind="switches" label={t('seatmap.switch')} value={draft.switch}
              onChange={(v) => patch({ switch: v, port: v === draft.switch ? draft.port : '' })} />
            <EntitySelect kind="ports" label={t('seatmap.portOnSwitch')} switchName={draft.switch} value={draft.port}
              onChange={(v) => patch({ port: v })} description={fallback('port')} />
          </SimpleGrid>
          <Fieldset legend={t('seatmap.findTitle')} variant="filled">
            <Text size="sm" c="dimmed" mb="xs">{t('seatmap.findHelp')}</Text>
            <Group gap="xs" align="flex-end" wrap="nowrap">
              <TextInput aria-label={t('seatmap.findMac')} value={lookFor} onChange={(e) => setLookFor(e.currentTarget.value)}
                styles={mono} placeholder="aa:bb:cc:dd:ee:ff" maxLength={20} style={{ flex: 1 }} />
              <Button variant="default" leftSection={<IconSearch size={16} />} loading={find.isPending}
                disabled={!lookFor.trim()} onClick={() => find.mutate()}>
                {t('seatmap.find')}
              </Button>
            </Group>
            <Text size="sm" mt={6} role="status" className={find.error ? 'fb-tone-err' : found ? 'fb-tone-ok' : undefined}>
              {find.error ? `✕ ${find.error.message}`
                : found ? (found.held_by ? t('seatmap.foundHeld', { ...found, seat: found.held_by }) : t('seatmap.found', { ...found })) : ''}
            </Text>
          </Fieldset>
          <Fieldset legend={t('seatmap.hints')} variant="unstyled">
            <Text size="sm" c="dimmed" mb="xs">{t('seatmap.hintsHelp')}</Text>
            <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
              <TextInput label={t('seatmap.ip')} value={draft.ip} onChange={set('ip')} description={fallback('ip')} styles={mono} placeholder="192.0.2.10" maxLength={45} />
              <TextInput label={t('seatmap.mac')} value={draft.mac} onChange={set('mac')} description={fallback('mac')} styles={mono} placeholder="aa:bb:cc:dd:ee:ff" maxLength={20} />
            </SimpleGrid>
          </Fieldset>
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
