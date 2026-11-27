import { Button, Group, Modal, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

/** "Leave without saving?" for LeaveGuard, loaded when it is first needed. */
export default function LeaveDialog({ onStay, onGo }: { onStay: () => void; onGo: () => void }) {
  const { t } = useTranslation()
  return (
    <Modal opened onClose={onStay} title={t('common.leave.title')} centered>
      <Text size="sm">{t('common.leave.text')}</Text>
      <Group justify="flex-end" mt="md">
        <Button variant="default" onClick={onStay} data-autofocus>{t('common.leave.stay')}</Button>
        <Button color="down" onClick={onGo}>{t('common.leave.go')}</Button>
      </Group>
    </Modal>
  )
}
