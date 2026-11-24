import { Alert, Button, Group, Modal, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconBellOff } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MuteTarget } from './mute'

const MINUTES = ['30', '60', '240', '720', '1440']

export function MuteDialog({ target, busy, error, onClose, onSave }: {
  target: MuteTarget | null
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (minutes: number, reason: string) => void
}) {
  const { t } = useTranslation()
  return (
    <Modal opened={!!target} onClose={onClose} title={t('problems.muteTitle', { name: target?.name })} closeButtonProps={{ 'aria-label': t('problems.cancel') }}>
      <MuteForm text={t(target?.kind === 'health' ? 'problems.muteTextService' : target?.kind === 'wifi' ? 'problems.muteTextAp' : 'problems.muteText')}
        busy={busy} error={error} onClose={onClose} onSave={onSave} />
    </Modal>
  )
}

function MuteForm({ text, busy, error, onClose, onSave }: {
  text: string
  busy: boolean
  error: string | null
  onClose: () => void
  onSave: (minutes: number, reason: string) => void
}) {
  const { t } = useTranslation()
  const [minutes, setMinutes] = useState<string | null>('60')
  const [reason, setReason] = useState('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(Number(minutes), reason.trim()) }}>
      <Stack gap="sm">
        <Text size="sm">{text}</Text>
        <Select label={t('problems.for')} data={MINUTES.map((m) => ({ value: m, label: t(`problems.minutes.${m}`) }))}
          value={minutes} onChange={setMinutes} allowDeselect={false} />
        <TextInput label={t('problems.reason')} value={reason} maxLength={200} onChange={(e) => setReason(e.currentTarget.value)} />
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('problems.cancel')}</Button>
          <Button type="submit" loading={busy} leftSection={<IconBellOff size={16} />}>{t('problems.mute')}</Button>
        </Group>
      </Stack>
    </form>
  )
}
