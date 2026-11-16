import { Button, Group, SegmentedControl, Tooltip } from '@mantine/core'
import { IconDeviceTv } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { type Mode, MODES, kioskHref } from './workspace'

/** The mode switch at the top of the plan workspace (see modes.ts). */
export function Modes({ mode, onMode, hall, params, checkin, canEdit }: {
  mode: Mode; onMode: (m: Mode) => void; hall: string; params: URLSearchParams; checkin: boolean; canEdit: boolean
}) {
  const { t } = useTranslation()
  return (
    <Group gap="xs" wrap="nowrap" className="fb-plan-modes">
      <SegmentedControl size="sm" value={mode} onChange={(v) => onMode(v as Mode)} aria-label={t('plan.modes.label')}
        data={MODES.filter((m) => (checkin || m !== 'checkin') && (canEdit || m !== 'edit')).map((m) => ({ value: m, label: t(`plan.modes.${m}`) }))} />
      <Tooltip label={t('plan.modes.kioskHint')}>
        <Button component="a" href={kioskHref(hall, params)} variant="default" leftSection={<IconDeviceTv size={16} aria-hidden="true" />}>
          {t('plan.modes.kiosk')}
        </Button>
      </Tooltip>
    </Group>
  )
}
