import { Group, SegmentedControl, Stack, Title } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ViewProps } from '@/pages/monitoring/pages'
import LancacheView from '../lancache/LancacheView'
import GamesView from './GamesView'
import { RANGES } from './ranges'

/** Traffic > Games and downloads: what the hall plays, then what the LAN cache served and saved.
 *  One range for both. The cache machine itself is a service: its row on Services (#1642). */
export default function GamesAndDownloads({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const [hours, setHours] = useState(24)
  return (
    <Stack gap="lg">
      {expanded && (
        <Group justify="flex-end">
          <SegmentedControl value={String(hours)} onChange={(v) => setHours(Number(v))} aria-label={t('games.range')}
            data={RANGES.map((h) => ({ value: String(h), label: t(`games.hours.${h}`) }))} />
        </Group>
      )}
      <GamesView expanded={expanded} hours={hours} />
      <section aria-labelledby="gd-downloads">
        <Title order={2} size="h4" id="gd-downloads" mb="sm">{t('lancache.title')}</Title>
        <LancacheView expanded={expanded} hours={hours} />
      </section>
    </Stack>
  )
}
