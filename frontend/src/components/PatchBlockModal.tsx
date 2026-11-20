import { Alert, Button, Checkbox, Group, Loader, Modal, Select, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { EntitySelect } from '@/components/EntitySelect'
import { RowsSelect } from '@/components/RowsSelect'
import type { BlockPlan, CableClash } from '@/api/types'

const SHOWN = 12   // preview rows before "…"

function Clash({ c }: { c: CableClash }) {
  const { t } = useTranslation()
  const text = c.kind === 'seat'
    ? t('cables.clashSeat', { seat: c.seat, cable: c.cable, other: c.other_port })
    : c.other_seat ? t('cables.clashPort', { port: c.port, cable: c.cable, seat: c.other_seat })
      : t('cables.clashPortFree', { port: c.port, cable: c.cable })
  return <Text size="sm">{text}{c.imported && <> {t('cables.clashImported')}</>}</Text>
}

/** "Switch X from Gi1/0/1, along rows C and D": a cable for every seat of the rows picked, in the
 *  order picked, whichever block they are in (issue #473, #1057). */
export function PatchBlockModal({ onClose, onDone }: {
  onClose: () => void; onDone: (made: BlockPlan) => void
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState({ rows: [] as string[], switch: '', first_port: 'Gi1/0/1', order: 'rows', reverse: false })
  const [replace, setReplace] = useState(false)
  const set = <K extends keyof typeof form>(k: K) => (v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }))
  const [typed] = useDebouncedValue(form, 300)
  const ready = Boolean(typed.rows.length && typed.switch.trim() && typed.first_port.trim())
  const preview = useQuery({
    queryKey: qk.blockPlan(typed),
    queryFn: () => post<BlockPlan>('/api/cables/block', { ...typed, dry_run: true }),
    enabled: ready,
    retry: false,
  })
  const make = useMutation({
    mutationFn: () => post<BlockPlan>('/api/cables/block', { ...form, replace }),
    onSuccess: onDone,
  })
  const plan = preview.data
  const settled = JSON.stringify(form) === JSON.stringify(typed)   // the preview shows what Make would do
  const blocked = Boolean(plan?.clashes.some((c) => c.imported))
  const needsReplace = Boolean(plan?.clashes.length) && !replace
  return (
    <Modal opened onClose={onClose} title={t('cables.patchTitle')} size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('cables.patchIntro')}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <RowsSelect label={t('cables.rows')} required value={form.rows} onChange={set('rows')} />
          <EntitySelect kind="switches" label={t('cables.switch')} required value={form.switch} onChange={set('switch')} />
          <EntitySelect kind="ports" switchName={form.switch} showUsed label={t('cables.firstPort')} required
            value={form.first_port} onChange={set('first_port')} />
          <Select label={t('cables.order')} allowDeselect={false} value={form.order} onChange={(v) => set('order')(v ?? 'rows')}
            data={[{ value: 'rows', label: t('cables.orderRows') }, { value: 'snake', label: t('cables.orderSnake') }]} />
          <Checkbox mt={{ sm: 30 }} label={t('cables.fromLast')} checked={form.reverse}
            onChange={(e) => set('reverse')(e.currentTarget.checked)} />
        </SimpleGrid>
        {ready && preview.isFetching && !plan && <Loader size="sm" aria-label={t('common.loading')} />}
        {preview.error && <Alert color="down" role="alert">{preview.error.message}</Alert>}
        {plan && !preview.error && (
          <>
            <Text size="sm" fw={600}>{t('cables.preview', { count: plan.cables.length })}</Text>
            <Table.ScrollContainer minWidth={320}>
              <Table withRowBorders={false} verticalSpacing={2}>
                <Table.Thead>
                  <Table.Tr><Table.Th>{t('cables.seat')}</Table.Th><Table.Th>{t('cables.switchPort')}</Table.Th></Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {plan.cables.slice(0, SHOWN).map((c) => (
                    <Table.Tr key={c.seat}><Table.Td>{c.seat}</Table.Td><Table.Td ff="monospace">{c.switch} {c.port}</Table.Td></Table.Tr>
                  ))}
                  {plan.cables.length > SHOWN && (
                    <Table.Tr>
                      <Table.Td c="dimmed">… {plan.cables[plan.cables.length - 1].seat}</Table.Td>
                      <Table.Td ff="monospace" c="dimmed">… {plan.cables[plan.cables.length - 1].port}</Table.Td>
                    </Table.Tr>
                  )}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {plan.clashes.length > 0 && (
              <Alert color={blocked ? 'down' : 'warn'}>
                <Stack gap={2}>{plan.clashes.map((c) => <Clash key={`${c.kind}-${c.seat}-${c.cable}`} c={c} />)}</Stack>
                {!blocked && <Checkbox mt="xs" label={t('cables.replace')} checked={replace}
                  onChange={(e) => setReplace(e.currentTarget.checked)} />}
              </Alert>
            )}
          </>
        )}
        {make.error && <Alert color="down" role="alert">{make.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={make.isPending} disabled={!plan || !plan.cables.length || blocked || needsReplace || preview.isFetching || !settled}
            onClick={() => make.mutate()}>
            {t('cables.create', { count: plan?.cables.length ?? 0 })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
