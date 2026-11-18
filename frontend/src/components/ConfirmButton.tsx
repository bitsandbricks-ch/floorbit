import { ActionIcon, Button, Group, Modal, Text, Tooltip, type ActionIconProps, type ButtonProps } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'

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

/** An icon button (a bin next to a row) that always asks first: one stray tap shouldn't delete. */
export function ConfirmIcon({
  label,
  onConfirm,
  question,
  tooltip,
  children,
  ...props
}: ActionIconProps & { label: string; onConfirm: () => void; question?: string; tooltip?: string; children: ReactNode }) {
  const { t } = useTranslation()
  const [opened, { open, close }] = useDisclosure(false)
  return (
    <>
      <Tooltip label={tooltip ?? label}>
        <ActionIcon variant="subtle" color="down" aria-label={label} {...props} onClick={open}>
          {children}
        </ActionIcon>
      </Tooltip>
      <Modal opened={opened} onClose={close} title={label} centered>
        <Text mb="lg">{question ?? t('common.areYouSure', { label })}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>{t('common.cancel')}</Button>
          <Button color="down" onClick={() => { close(); onConfirm() }}>{t('common.confirm')}</Button>
        </Group>
      </Modal>
    </>
  )
}
