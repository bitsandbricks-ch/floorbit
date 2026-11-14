import { Alert, Button, Group, Modal, PasswordInput, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface PortRequest {
  action: 'shutdown' | 'enable' | 'bounce'
  /** Shut a finding's port: the server takes the switch and port from the finding. */
  finding?: string
  /** A seat's port: the server finds the switch and port from the seat. */
  seat?: string
  switch?: string
  port?: string
  where: string
}

/** Confirm a port action, with the tech's own switch login when the plugin needs one.
 *  The password lives only in this dialog's state and is cleared on close. */
export function PortDialog({
  request,
  needsLogin,
  busy,
  error,
  matchSeat,
  onClose,
  onConfirm,
}: {
  request: PortRequest | null
  needsLogin: boolean
  busy: boolean
  error: string | null
  /** The match zone, once the server said this port is behind a tournament seat (issue #31). */
  matchSeat?: string | null
  onClose: () => void
  onConfirm: (login: { username?: string; password?: string; reason?: string; confirm_match?: boolean }) => void
}) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const shut = request?.action === 'shutdown'
  const bounce = request?.action === 'bounce'
  const close = () => {
    setPassword('')
    setReason('')
    onClose()
  }
  return (
    <Modal opened={!!request} onClose={close} title={t(bounce ? 'security.bounceTitle' : shut ? 'security.shutTitle' : 'security.enableTitle', { where: request?.where })}>
      <form
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault()
          const login = needsLogin ? { username: username.trim(), password } : {}
          setPassword('')
          onConfirm({ ...login, reason: reason.trim() || undefined, ...(matchSeat ? { confirm_match: true } : {}) })
        }}
      >
        <Stack gap="sm">
          <Text size="sm">{t(bounce ? 'security.bounceText' : shut ? 'security.shutText' : 'security.enableText')}</Text>
          {shut && (
            <TextInput label={t('security.reason')} value={reason} maxLength={200} onChange={(e) => setReason(e.currentTarget.value)} />
          )}
          {needsLogin && (
            <>
              <TextInput label={t('security.username')} value={username} required maxLength={64} autoComplete="off"
                onChange={(e) => setUsername(e.currentTarget.value)} />
              <PasswordInput label={t('security.password')} value={password} required maxLength={256} autoComplete="off"
                onChange={(e) => setPassword(e.currentTarget.value)} />
              <Text size="xs" c="dimmed">{t('security.loginHint')}</Text>
            </>
          )}
          {matchSeat ? <Alert color="warn" role="alert" title={t('security.matchTitle', { zone: matchSeat })}>{t('security.matchText')}</Alert>
            : error && <Alert color="down" role="alert">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>{t('common.cancel')}</Button>
            <Button type="submit" color={shut ? 'down' : undefined} loading={busy}>
              {matchSeat ? t('security.matchConfirm') : t(bounce ? 'security.bounce' : shut ? 'security.shut' : 'security.enable')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
