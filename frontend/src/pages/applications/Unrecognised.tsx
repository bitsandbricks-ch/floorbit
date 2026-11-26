import { Button, Group, Paper, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ApplicationsAnswer } from '@/api/applications'

const SHOWN = 8

/** The busiest sites nothing names yet (issue #1612), each a step away from an application. Only
 *  sites 5 or more seats used, as everywhere else on the page. */
export function Unrecognised({ rows, canEdit, onMake }: {
  rows: ApplicationsAnswer['unrecognised']; canEdit: boolean; onMake: (site: string) => void
}) {
  const { t } = useTranslation()
  const [all, setAll] = useState(false)
  if (!rows.length) return null
  const shown = all ? rows : rows.slice(0, SHOWN)
  return (
    <Paper withBorder radius="md" p="md" aria-label={t('applicationShare.unrecognised')}>
      <Stack gap="xs">
        <div>
          <Text fw={600}>{t('applicationShare.unrecognised')}</Text>
          <Text size="sm" c="dimmed">{t('applicationShare.unrecognisedHelp')}</Text>
        </div>
        {shown.map((r) => (
          <Group key={r.site} justify="space-between" wrap="nowrap" gap="xs">
            <Text size="sm" ff="monospace" truncate>{r.site}</Text>
            <Group gap="sm" wrap="nowrap">
              <Text size="xs" c="dimmed">{t('applicationShare.seatsLookups', { seats: r.seats, lookups: r.lookups })}</Text>
              {canEdit && (
                <Button size="compact-xs" variant="default" onClick={() => onMake(r.site)}>{t('applicationShare.make')}</Button>
              )}
            </Group>
          </Group>
        ))}
        {rows.length > SHOWN && (
          <Group><Button size="compact-xs" variant="subtle" onClick={() => setAll((a) => !a)}>
            {all ? t('applicationShare.fewer') : t('applicationShare.allOf', { count: rows.length })}
          </Button></Group>
        )}
      </Stack>
    </Paper>
  )
}
