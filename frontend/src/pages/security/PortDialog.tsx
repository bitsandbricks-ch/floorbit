import { Alert, Button, Group, Modal, PasswordInput, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface PortRequest {
  action: 'shutdown' | 'enable'
  /** Shut a finding's port: the server takes the switch and port from the finding. */
  finding?: string
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
  onClose,
  onConfirm,
}: {
  request: PortRequest | null
  needsLogin: boolean
  busy: boolean
  error: string | null
  onClose: () => void
  onConfirm: (login: { username?: string; password?: string; reason?: string }) => void
}) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const shut = request?.action === 'shutdown'
  const close = () => {
    setPassword('')
    setReason('')
    onClose()
  }
  return (
    <Modal opened={!!request} onClose={close} title={shut ? t('security.shutTitle', { where: request?.where }) : t('security.enableTitle', { where: request?.where })}>
      <form
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault()
          const login = needsLogin ? { username: username.trim(), password } : {}
          setPassword('')
          onConfirm({ ...login, reason: reason.trim() || undefined })
        }}
      >
        <Stack gap="sm">
          <Text size="sm">{shut ? t('security.shutText') : t('security.enableText')}</Text>
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
          {error && <Alert color="down" role="alert">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>{t('common.cancel')}</Button>
            <Button type="submit" color={shut ? 'down' : undefined} loading={busy}>
              {shut ? t('security.shut') : t('security.enable')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
