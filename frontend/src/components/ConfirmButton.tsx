import { Button, Group, Modal, Text, type ButtonProps } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useTranslation } from 'react-i18next'

/** A button that asks first when `danger` is set (a plugin action marked danger: true). */
export function ConfirmButton({
  label,
  danger,
  onConfirm,
  question,
  ...props
}: ButtonProps & { label: string; danger?: boolean; onConfirm: () => void; title?: string; question?: string }) {
  const { t } = useTranslation()
  const [opened, { open, close }] = useDisclosure(false)
  return (
    <>
      <Button color={danger ? 'down' : undefined} {...props} onClick={danger ? open : onConfirm}>
        {label}
      </Button>
      {danger && (
        <Modal opened={opened} onClose={close} title={label} centered>
          <Text mb="lg">{question ?? t('common.areYouSure', { label })}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button
              color="down"
              onClick={() => {
                close()
                onConfirm()
              }}
            >
              {t('common.confirm')}
            </Button>
          </Group>
        </Modal>
      )}
    </>
  )
}
