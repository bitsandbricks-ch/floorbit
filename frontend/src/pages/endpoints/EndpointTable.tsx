import { Anchor, Badge, Group, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { EndpointRow } from '@/api/types'
import { DataTable } from '@bitsandbricks/ui'
import { ago, dateTime } from '@/lib/time'

// On a phone each row is a card: IP, MAC, port and seat first, then when it was seen.
// Seen in the last two minutes: the collector looks every minute.
const NOW_WINDOW = 120

/** Where machines were seen: the IP and MAC history's table, on its page and on a device's
 *  MAC and IP tab (issue #903). ``now`` is when the answer came, so a row doesn't stay "now". */
export function EndpointTable({ rows, now, label }: { rows: EndpointRow[]; now: number; label: string }) {
  const { t } = useTranslation()
  const portLink = (r: EndpointRow) => (r.port
    ? <Anchor component={Link} to={`/endpoints?device=${encodeURIComponent(r.device)}&port=${encodeURIComponent(r.port)}`}>{r.device} {r.port}</Anchor>
    : <Text span c="dimmed">{t('endpoints.arpOnly', { device: r.device })}</Text>)
  return (
    <DataTable label={label} rows={rows} rowKey={(r) => `${r.mac}|${r.ip}|${r.device}|${r.port}|${r.first_seen}`}
      defaultSort={{ id: 'seen', desc: true }} minWidth={760} bare striped cards
      columns={[
        { id: 'ip', header: t('endpoints.col.ip'), sort: (r) => r.ip ?? '', mono: true, card: 'inline', cell: (r) => r.ip ?? '–' },
        { id: 'mac', header: t('endpoints.col.mac'), sort: (r) => r.mac, mono: true, card: 'inline', cell: (r) => r.mac },
        { id: 'port', header: t('endpoints.col.port'), sort: (r) => `${r.device} ${r.port}`, card: 'inline', cell: (r) => portLink(r) },
        { id: 'seat', header: t('endpoints.col.seat'), sort: (r) => r.seat ?? '', card: 'inline', cell: (r) =>
          (r.seat ? <Anchor component={Link} to={`/endpoints?seat=${encodeURIComponent(r.seat)}`}>{r.seat}</Anchor> : '–') },
        { id: 'vlan', header: t('endpoints.col.vlan'), sort: (r) => r.vlan ?? -1, hideOnPhone: true, cell: (r) => r.vlan ?? '–' },
        { id: 'seen', header: t('endpoints.col.seen'), sort: (r) => r.last_seen, cell: (r) => (
          <Group gap={6} wrap="nowrap">
            {now - r.last_seen < NOW_WINDOW
              ? <Badge color="up" variant="light" tt="none">{t('endpoints.now')}</Badge>
              : <Text span size="sm">{ago(r.last_seen)}</Text>}
            <Text span size="xs" c="dimmed">{t('endpoints.since', { when: dateTime(r.first_seen) })}</Text>
          </Group>
        ) },
      ]} />
  )
}
