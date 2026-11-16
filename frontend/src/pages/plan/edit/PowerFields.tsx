import { Badge, Button, Group, Modal, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Circuit, PowerOverview } from '@/api/types'
import { nextName } from './tools'

const STATE_COLOR: Record<string, string> = { ok: 'up', warn: 'warn', crit: 'down', tripped: 'down', unknown: 'gray' }

/** A new distribution board where the plan was clicked: its name (the next free one). */
export function PlaceBoardDialog({ opened, names, onClose, onCreate }: {
  opened: boolean; names: string[]; onClose: () => void; onCreate: (body: { name: string; location: string }) => Promise<boolean>
}) {
  if (!opened) return null
  return <BoardForm key={names.join('|')} names={names} onClose={onClose} onCreate={onCreate} />
}

function BoardForm({ names, onClose, onCreate }: {
  names: string[]; onClose: () => void; onCreate: (body: { name: string; location: string }) => Promise<boolean>
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(() => (names.length ? nextName(names[names.length - 1], names) : 'DB-1'))
  const [location, setLocation] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      await onCreate({ name: name.trim(), location: location.trim() })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal opened onClose={onClose} title={t('plan.edit.board.title')}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          <TextInput label={t('plan.edit.board.name')} value={name} maxLength={40} required data-autofocus onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput label={t('plan.edit.board.location')} placeholder={t('plan.edit.board.locationHint')} value={location} maxLength={80}
            onChange={(e) => setLocation(e.currentTarget.value)} />
          <Text size="xs" c="dimmed">{t('plan.edit.board.help')}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={!name.trim()}>{t('plan.edit.board.place')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

/** A selected board: its circuits with their load, a new circuit, and (with seat blocks or switches
 *  selected too) feeding them from one of its circuits. */
export function BoardFields({ board, feedable, onAddCircuit, onFeed }: {
  board: string
  /** How many seat blocks and switches are selected with the board. */
  feedable: number
  onAddCircuit: (name: string) => Promise<void>
  onFeed: (circuit: Circuit) => Promise<void>
}) {
  const { t } = useTranslation()
  const power = useQuery({ queryKey: qk.power, queryFn: () => get<PowerOverview>('/api/power'), staleTime: 10_000 })
  const circuits = (power.data?.circuits ?? []).filter((c) => c.board === board)
  const [name, setName] = useState('')
  const [pick, setPick] = useState<string | null>(null)
  const chosen = circuits.find((c) => c.id === pick) ?? null
  return (
    <>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('plan.edit.board.circuits', { count: circuits.length })}</Text>
        <Stack gap={4}>
          {circuits.map((c) => (
            <Group key={c.id} justify="space-between" wrap="nowrap" gap="xs">
              <div style={{ minWidth: 0 }}>
                <Text size="sm" truncate>{c.name}</Text>
                <Text size="xs" c="dimmed" truncate>{c.feeds_label || t('plan.edit.board.feedsNothing')}</Text>
              </div>
              <Badge variant="light" color={STATE_COLOR[c.state] ?? 'gray'}>{c.state === 'tripped' ? t('plan.power.tripped') : c.load_pct == null ? '–' : `${Math.round(c.load_pct)} %`}</Badge>
            </Group>
          ))}
        </Stack>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) void onAddCircuit(name.trim()).then(() => { setName(''); void power.refetch() }) }}>
        <Group gap="xs" wrap="nowrap" align="flex-end">
          <TextInput style={{ flex: 1 }} label={t('plan.edit.board.newCircuit')} placeholder={t('plan.edit.board.circuitHint')} value={name} maxLength={40}
            onChange={(e) => setName(e.currentTarget.value)} />
          <Button type="submit" variant="default" leftSection={<IconPlus size={14} />} disabled={!name.trim()}>{t('plan.edit.board.add')}</Button>
        </Group>
      </form>
      {feedable > 0 && circuits.length > 0 && (
        <Group gap="xs" wrap="nowrap" align="flex-end">
          <Select style={{ flex: 1 }} label={t('plan.edit.board.feed', { count: feedable })} value={pick} onChange={setPick}
            data={circuits.map((c) => ({ value: c.id, label: c.name }))} />
          <Button disabled={!chosen} onClick={() => chosen && void onFeed(chosen).then(() => power.refetch())}>{t('plan.edit.board.feedGo')}</Button>
        </Group>
      )}
      {feedable === 0 && <Text size="xs" c="dimmed">{t('plan.edit.board.feedHint')}</Text>}
      <Text size="xs" c="dimmed"><a href="/power">{t('plan.edit.board.more')}</a></Text>
    </>
  )
}
