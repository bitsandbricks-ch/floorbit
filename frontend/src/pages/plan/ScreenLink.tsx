import { ActionIcon, Tooltip } from '@mantine/core'
import { IconDeviceTv } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { kioskHref } from './workspace'

/** The big-screen link in the plan's top bar: the same hall, layers and filter without the chrome. */
export function ScreenLink({ hall, params }: { hall: string; params: URLSearchParams }) {
  const { t } = useTranslation()
  return (
    <Tooltip label={t('plan.modes.kioskHint')}>
      <ActionIcon component="a" href={kioskHref(hall, params)} variant="default" size="md" aria-label={t('plan.modes.kiosk')}>
        <IconDeviceTv size={16} aria-hidden="true" />
      </ActionIcon>
    </Tooltip>
  )
}
