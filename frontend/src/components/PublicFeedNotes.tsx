import { Button, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { clock } from '@/lib/time'

/** The small pill on top while a public page shows old data because the server can't be reached. */
export function StaleNote({ since }: { since: number | null }) {
  const { t } = useTranslation()
  return (
    <p className="fb-stale-note" role="status">
      {t('publicPages.stale', { time: since ? clock(since / 1000) : '–' })}
    </p>
  )
}

/** A public page an admin switched off (the server answers 404). */
export function PageOff({ title, text }: { title: string; text: string }) {
  return (
    <Paper withBorder radius="lg" p="lg">
      <Stack gap={4}>
        <Title order={1} size="h4" c="dimmed">{title}</Title>
        <Text role="alert">{text}</Text>
      </Stack>
    </Paper>
  )
}

/** The first load failed: no data to show yet. */
export function FeedFailed({ title, onRetry }: { title: string; onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="lg">
      <Stack gap="sm" align="flex-start">
        <Title order={1} size="h4">{title}</Title>
        <Text c="dimmed">{t('publicPages.unreachable')}</Text>
        <Button variant="default" onClick={onRetry}>{t('publicPages.retry')}</Button>
      </Stack>
    </Paper>
  )
}
