import { Stack, Table, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { SeatSpeedTest } from '@/api/types'
import { minutesAgo } from './model'

/** The player's own speed tests from the seat's help page (issue #182), newest first. A test from
 *  before the link last changed is marked, so "slow at 14:00" isn't read as "slow now". */
export function SeatSpeedTests({ tests, lastChange }: { tests: SeatSpeedTest[]; lastChange: number | null }) {
  const { t } = useTranslation()
  const num = (v: number | null) => (v === null ? '–' : String(Math.round(v)))
  const ago = (at: number) => {
    const min = minutesAgo(at)
    return min < 120 ? t('plan.speed.minAgo', { count: min }) : t('plan.speed.hAgo', { count: Math.round(min / 60) })
  }
  return (
    <Stack gap={4}>
      <Title order={3} size="h5">{t('plan.speed.title')}</Title>
      <Table withRowBorders={false} verticalSpacing={2} fz="sm" className="fb-speed-tests">
        <Table.Thead>
          <Table.Tr>
            <Table.Th fw={500} c="dimmed">{t('plan.speed.when')}</Table.Th>
            <Table.Th fw={500} c="dimmed" ta="right">{t('plan.speed.down')}</Table.Th>
            <Table.Th fw={500} c="dimmed" ta="right">{t('plan.speed.up')}</Table.Th>
            <Table.Th fw={500} c="dimmed" ta="right">{t('plan.speed.ping')}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tests.map((x) => (
            <Table.Tr key={x.at}>
              <Table.Td>
                {ago(x.at)}
                {lastChange !== null && x.at < lastChange && <Text span size="xs" c="dimmed"> · {t('plan.speed.before')}</Text>}
              </Table.Td>
              <Table.Td ta="right">{num(x.down_mbps)}</Table.Td>
              <Table.Td ta="right">{num(x.up_mbps)}</Table.Td>
              <Table.Td ta="right">{num(x.ping_ms)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}
