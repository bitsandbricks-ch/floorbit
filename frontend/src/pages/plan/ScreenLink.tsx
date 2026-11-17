import { ActionIcon, Tooltip } from '@mantine/core'
import { IconDeviceTv, IconLayoutDashboard } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { kioskHref } from './workspace'

/** The big-screen links in the plan's top bar: the kiosk (the same hall, layers and filter without
 * the chrome) and, beside it, the dashboards that put the plan on a screen with other widgets. */
export function ScreenLink({ hall, params }: { hall: string; params: URLSearchParams }) {
  const { t } = useTranslation()
  return (
    <>
      <Tooltip label={t('plan.modes.kioskHint')}>
        <ActionIcon component="a" href={kioskHref(hall, params)} variant="default" size="md" aria-label={t('plan.modes.kiosk')}>
          <IconDeviceTv size={16} aria-hidden="true" />
        </ActionIcon>
      </Tooltip>
      <Tooltip label={t('plan.modes.dashboardsHint')}>
        <ActionIcon component={Link} to="/dashboards" variant="default" size="md" aria-label={t('plan.modes.dashboards')}>
          <IconLayoutDashboard size={16} aria-hidden="true" />
        </ActionIcon>
      </Tooltip>
    </>
  )
}
