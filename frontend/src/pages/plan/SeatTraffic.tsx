import { Alert, Button, Group, Stack, Table, Text, Title } from '@mantine/core'
import { IconChartBar } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchSeatTraffic } from '@/api/flowLookup'
import { qk } from '@/api/keys'
import { useTrafficCategories } from '@/api/trafficCategories'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { bytes } from '@/pages/traffic/format'
import { MixBar } from '@/pages/traffic/TrafficView'

/** The seat's traffic over 24 hours (#1481 B): volume, categories, top applications and the
 *  networks' owners it talked to. Only on a click, because every look goes to the audit log. */
export function SeatTraffic({ seat }: { seat: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const cats = useTrafficCategories()
  const q = useQuery({ queryKey: qk.seatTraffic(seat), queryFn: () => fetchSeatTraffic(seat), enabled: open,
    staleTime: 60_000, retry: false })
  if (!open) {
    return (
      <Stack gap={4}>
        <Title order={3} size="h5">{t('seatTraffic.title')}</Title>
        <Group>
          <Button variant="default" size="xs" leftSection={<IconChartBar size={14} />} onClick={() => setOpen(true)}>
            {t('seatTraffic.show')}
          </Button>
        </Group>
        <Text size="xs" c="dimmed">{t('seatTraffic.audited')}</Text>
      </Stack>
    )
  }
  const d = q.data
  const failed = d?.agents.filter((a) => a.error) ?? []
  const list = (rows: { key: string; name: string; bytes: number }[]) => (
    <Table withRowBorders verticalSpacing={4}>
      <Table.Tbody>
        {rows.map((r, i) => (
          <Table.Tr key={r.key}>
            <Table.Td w={24} c="dimmed">{i + 1}</Table.Td>
            <Table.Td>{r.name}</Table.Td>
            <Table.Td ta="right" fw={600} style={{ whiteSpace: 'nowrap' }}>{bytes(r.bytes)}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
  return (
    <Stack gap="xs" aria-label={t('seatTraffic.title')} role="region">
      <Title order={3} size="h5">{t('seatTraffic.title')}</Title>
      {q.isPending && <LoadingState />}
      {q.error && <ErrorBanner error={q.error} />}
      {d && (
        <>
          <div>
            <Text size="xs" c="dimmed">{t('seatTraffic.hours', { count: d.hours })}</Text>
            <Text fw={700} size="xl">{bytes(d.bytes)}</Text>
          </div>
          {d.bytes > 0 && <MixBar mix={d.categories} label={t('seatTraffic.mix', { seat })} />}
          {d.applications.length > 0 && (
            <div>
              <Text fw={600} size="sm">{t('seatTraffic.applications')}</Text>
              {list(d.applications.map((a) => ({ key: a.name, name: a.name === 'Other' ? cats.label('other') : a.name, bytes: a.bytes })))}
            </div>
          )}
          {d.owners.length > 0 && (
            <div>
              <Text fw={600} size="sm">{t('seatTraffic.owners')}</Text>
              {list(d.owners.map((o) => ({ key: String(o.asn), name: `${o.name} (AS${o.asn})`, bytes: o.bytes })))}
            </div>
          )}
          {d.bytes === 0 && <Text size="sm" c="dimmed">{t('seatTraffic.none')}</Text>}
          {d.stopped && <Alert color="yellow" variant="light">{t('seatTraffic.stopped')}</Alert>}
          {failed.map((a) => (
            <Alert key={a.name} color="yellow" variant="light">{t('seatTraffic.agentFailed', { name: a.name, error: a.error })}</Alert>
          ))}
          <Text size="xs" c="dimmed">{t('seatTraffic.audited')}</Text>
        </>
      )}
    </Stack>
  )
}
