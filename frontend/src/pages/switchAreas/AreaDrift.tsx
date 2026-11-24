import { Alert, Anchor, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { AreaDrift as Drift } from '@/api/types'

/** A port found for a seat on a switch whose area doesn't hold that seat (issue #1094): said where
 *  it is found, with the way to Switch areas, so the pin or the patch gets fixed on the spot. */
export function AreaDrift({ drift }: { drift: Drift | null | undefined }) {
  const { t } = useTranslation()
  if (!drift) return null
  return (
    <Alert color="warn" variant="light">
      <Stack gap={4}>
        <Text size="sm">{t(`switchAreas.found.${drift.kind}`, { switch: drift.switch, area: drift.area.join(', '), row: drift.row })}</Text>
        <Anchor size="sm" href="/switch-areas">{t('switchAreas.found.open')}</Anchor>
      </Stack>
    </Alert>
  )
}
