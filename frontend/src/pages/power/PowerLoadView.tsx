import { Anchor, Badge, Group, Loader, Stack, Table, Text } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { usePower } from '@/api/queries'
import { ErrorBanner } from '@/components/ui'
import type { ViewProps } from '@/widgets/views'
import { Load } from './parts'
import { ORDER, TONE } from './state'

/** How loaded the circuits are. Small, the counts and the circuits that need a look; opened up,
 *  every circuit by board. Boards, circuits and readings are set up on the Electrics page. */
export default function PowerLoadView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const power = usePower()
  useLiveEvent('power.changed', () => void client.invalidateQueries({ queryKey: qk.power }))
  const data = power.data
  if (power.isPending || !data) return <><ErrorBanner error={power.error} /><Loader size="sm" aria-label={t('common.loading')} /></>
  if (!data.enabled) return <Text c="dimmed">{t('power.off')}</Text>
  const shown = expanded ? data.circuits : data.circuits.filter((c) => c.state !== 'ok' && c.state !== 'unknown')
  const boardName = (id: string) => data.boards.find((b) => b.id === id)?.name ?? ''
  return (
    <Stack gap="sm">
      <ErrorBanner error={power.error} />
      {data.circuits.length > 0 && (
        <Group gap="xs" aria-live="polite">
          {ORDER.filter((s) => data.counts[s]).map((s) => (
            <Badge key={s} color={TONE[s]} variant={s === 'ok' || s === 'unknown' ? 'light' : 'filled'} size="lg" tt="none">
              {t(`power.count.${s}`, { count: data.counts[s] })}
            </Badge>
          ))}
        </Group>
      )}
      {!data.circuits.length ? <Text c="dimmed">{t('power.noBoards')}</Text> : !shown.length ? (
        <Text c="dimmed">{t('power.allFine')}</Text>
      ) : (
        <Table.ScrollContainer minWidth={420}>
          <Table verticalSpacing="xs">
            <Table.Tbody>
              {shown.map((c) => (
                <Table.Tr key={c.id}>
                  <Table.Td>
                    <Text size="sm" fw={600}>{c.name}</Text>
                    <Text size="xs" c="dimmed">{boardName(c.board)}</Text>
                  </Table.Td>
                  <Table.Td><Load c={c} /></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Anchor href="/power" size="sm">{t('power.manage')}</Anchor>
    </Stack>
  )
}
