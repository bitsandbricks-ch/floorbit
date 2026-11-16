import { Badge, Button, Group, Loader, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { SwitchDetails } from '@/api/types'
import { SeatGlyph } from './SeatMap'
import { ErrorBanner } from '@/components/ui'

const TONE: Record<string, string> = { online: 'up', offline: 'down' }

/** One switch and the seats it serves (issue #176): before walking to it, which players it takes down. */
export function SwitchPanel({ name, onSeat, onClose }: { name: string; onSeat: (seat: string) => void; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const q = useQuery({ queryKey: qk.planSwitch(name), queryFn: () => get<SwitchDetails>(`/api/plan/switches/${encodeURIComponent(name)}`) })
  const w = q.data
  const clock = (ts: number) => new Date(ts * 1000).toLocaleString(i18n.language, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <Stack gap="sm" className="fb-inspector" aria-live="polite">
      <Group justify="space-between" wrap="nowrap">
        <Title order={2} size="h3">{w?.name ?? name}</Title>
        <Button variant="subtle" size="compact-sm" onClick={onClose}>{t('plan.close')}</Button>
      </Group>
      {q.isPending && <Loader size="sm" aria-label={t('common.loading')} />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {w && (
        <>
          <Group gap="xs">
            <Badge color={TONE[w.status] ?? 'gray'} variant={w.status === 'online' ? 'filled' : 'outline'}>{t(`plan.state.${w.status}`, { defaultValue: w.status })}</Badge>
            {w.since && <Text size="sm" c="dimmed">{t('plan.since', { time: clock(w.since) })}</Text>}
            {w.model && <Text size="sm" c="dimmed">{w.model}</Text>}
          </Group>
          <Text>{t('plan.blockPanel.carries', { online: w.online, count: w.seats.length })}</Text>
          {w.seats.length === 0 ? (
            <Text size="sm" c="dimmed">{t('plan.switchPanel.noSeats')}</Text>
          ) : (
            <Table withRowBorders={false} verticalSpacing={2} aria-label={t('plan.switchPanel.seats')}>
              <Table.Thead>
                <Table.Tr><Table.Th>{t('plan.switchPanel.port')}</Table.Th><Table.Th>{t('plan.list.seat')}</Table.Th><Table.Th>{t('plan.list.state')}</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {w.seats.map((r) => (
                  <Table.Tr key={r.seat}>
                    <Table.Td><code>{r.port}</code></Table.Td>
                    <Table.Td><UnstyledButton fw={700} className="fb-seat-list-seat" onClick={() => onSeat(r.seat)}>{r.seat}</UnstyledButton></Table.Td>
                    <Table.Td>
                      <Group gap={6} wrap="nowrap">
                        <svg viewBox="-4 -4 40 40" width={16} height={16} aria-hidden="true" className="fb-plan"><SeatGlyph seat={{ state: r.state, problems: r.problems }} size={32} detail={false} /></svg>
                        {t(`plan.state.${r.state}`)}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {(w.links?.length ?? 0) > 0 && (
            <Table withRowBorders={false} verticalSpacing={2} aria-label={t('plan.switchPanel.links')}>
              <Table.Thead>
                <Table.Tr><Table.Th>{t('plan.switchPanel.port')}</Table.Th><Table.Th>{t('plan.switchPanel.to')}</Table.Th><Table.Th>{t('plan.switchPanel.lldp')}</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {w.links!.map((l) => (
                  <Table.Tr key={l.id}>
                    <Table.Td><code>{l.port}</code></Table.Td>
                    <Table.Td className={l.issue === 'down' ? 'fb-tone-err' : l.issue === 'slow' ? 'fb-tone-warn' : undefined}>
                      <code>{l.to} {l.to_port}</code>
                    </Table.Td>
                    <Table.Td className={l.lldp?.state === 'other' ? 'fb-tone-warn' : undefined}>
                      {l.lldp ? t(`plan.switchPanel.lldpState.${l.lldp.state}`, { there: `${l.lldp.remote ?? ''} ${l.lldp.remote_port ?? ''}`.trim() }) : '–'}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {(w.neighbours?.length ?? 0) > 0 && (
            <Stack gap={2}>
              <Text size="sm" fw={600}>{t('plan.switchPanel.neighbours')}</Text>
              <Text size="xs" c="dimmed">{t('plan.switchPanel.neighboursHint')}</Text>
              {w.neighbours!.map((n) => (
                <Text key={n.port} size="sm"><code>{n.port}</code> → <code>{n.remote} {n.remote_port}</code>{n.protocol && <Text span size="xs" c="dimmed"> {n.protocol.toUpperCase()}</Text>}</Text>
              ))}
            </Stack>
          )}
        </>
      )}
    </Stack>
  )
}
