import { Alert, Anchor, Badge, Button, Group, Loader, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { BlockDetails } from '@/api/types'
import { rate } from './model'

const TONE: Record<string, string> = { online: 'up', offline: 'down' }

/** A whole seat block at a glance (issue #174): when half a block goes dark, is it one switch? */
export function BlockPanel({ name, onSeat, onSwitch, onClose }: {
  name: string; onSeat: (seat: string) => void; onSwitch?: (name: string) => void; onClose: () => void
}) {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.planBlock(name), queryFn: () => get<BlockDetails>(`/api/plan/blocks/${encodeURIComponent(name)}`) })
  const b = q.data
  const part = (n: number, total: number) => `${total ? (n / total) * 100 : 0}%`
  return (
    <Stack gap="sm" className="fb-inspector" aria-live="polite">
      <Group justify="space-between" wrap="nowrap">
        <Title order={2} size="h3">{t('plan.blockPanel.title', { name })}</Title>
        <Button variant="subtle" size="compact-sm" onClick={onClose}>{t('plan.close')}</Button>
      </Group>
      {q.isPending && <Loader size="sm" aria-label={t('common.loading')} />}
      {q.error && <Alert color="down" role="alert">{t('common.error', { message: q.error.message })}</Alert>}
      {b && (
        <>
          <Text>{t('plan.blockPanel.carries', { online: b.online, count: b.seats })}</Text>
          <div className="fb-block-bar" aria-hidden="true">
            <i className="on" style={{ width: part(b.online, b.seats) }} />
            <i className="off" style={{ width: part(b.offline, b.seats) }} />
            <i className="unk" style={{ width: part(b.unknown, b.seats) }} />
          </div>
          <Table withRowBorders={false} verticalSpacing={4}>
            <Table.Tbody>
              {([['state.online', b.online], ['state.offline', b.offline], ['state.unknown', b.unknown]] as const).map(([k, n]) => (
                <Table.Tr key={k}><Table.Th scope="row" fw={500} c="dimmed" w="50%">{t(`plan.${k}`)}</Table.Th><Table.Td>{n}</Table.Td></Table.Tr>
              ))}
              {b.checked_in !== null && <Table.Tr><Table.Th scope="row" fw={500} c="dimmed">{t('plan.checkin')}</Table.Th><Table.Td>{b.checked_in}</Table.Td></Table.Tr>}
              <Table.Tr><Table.Th scope="row" fw={500} c="dimmed">{t('plan.traffic')}</Table.Th><Table.Td>{rate(b.bps)}</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
          <Stack gap={4}>
            <Title order={3} size="h5">{t('plan.blockPanel.switches')}</Title>
            {b.switches.length === 0 && <Text size="sm" c="dimmed">{t('plan.blockPanel.noSwitches')}</Text>}
            {b.switches.map((w) => (
              <Group key={w.name} justify="space-between" wrap="nowrap" gap="xs">
                <Group gap="xs" wrap="nowrap">
                  {onSwitch
                    ? <Anchor component="button" type="button" size="sm" fw={600} onClick={() => onSwitch(w.name)}>{w.name}</Anchor>
                    : <Text size="sm" fw={600}>{w.name}</Text>}
                  <Badge size="sm" color={TONE[w.status] ?? 'gray'} variant={w.status === 'offline' ? 'filled' : 'light'}>{t(`plan.state.${w.status}`, { defaultValue: w.status })}</Badge>
                </Group>
                {/* One empty seat is normal; a switch with none of its seats up is the outage. */}
                <Text size="sm" c={w.status === 'offline' || (w.seats > 0 && w.online === 0) ? 'down' : 'dimmed'}>{t('plan.blockPanel.carries', { online: w.online, count: w.seats })}</Text>
              </Group>
            ))}
            {b.no_port > 0 && <Text size="xs" c="dimmed">{t('plan.blockPanel.noPort', { count: b.no_port })}</Text>}
          </Stack>
          {b.problems.length > 0 && (
            <Stack gap={4}>
              <Title order={3} size="h5">{t('plan.problems')}</Title>
              <Group gap="xs">
                {b.problems.map((p) => (
                  <UnstyledButton key={p.seat} onClick={() => onSeat(p.seat)} className="fb-block-seat">
                    <Badge color="down" variant="light" size="lg">{p.seat} · {p.problems}</Badge>
                  </UnstyledButton>
                ))}
              </Group>
            </Stack>
          )}
        </>
      )}
    </Stack>
  )
}
