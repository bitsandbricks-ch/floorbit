import { Alert, Badge, Button, Group, Stack, Table, Text } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { SwitchArea, SwitchAreas as Areas } from '@/api/types'
import { Layout } from '@/components/Layout'
import { Card, PageHead } from '@bitsandbricks/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { AreaEditor } from './switchAreas/AreaEditor'

const HOW_COLOR = { manual: 'blue', learned: 'up', plan: 'gray', upstream: 'gray', todo: 'warn', excluded: 'gray' } as const

/** Which seats each switch serves (issue #948, docs/switch-areas.md): pinned, learned from the
 *  seats mapped to its ports, or from where it is drawn on the plan. Disagreements are shown, never
 *  settled silently. The check-in lookup asks a seat's own switches first. */
export default function SwitchAreas() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('seats.edit')
  // A phone shows each switch as a card (the shared table-stack look) instead of a table cut off at the side.
  const phone = useMediaQuery('(max-width: 48em)', false, { getInitialValueInEffect: false })
  const query = useQuery({ queryKey: qk.switchAreas, queryFn: () => get<Areas>('/api/switch-areas') })
  useLiveEvent('switch-areas.changed', () => void qc.invalidateQueries({ queryKey: qk.switchAreas }))
  const [editing, setEditing] = useState<SwitchArea | null>(null)
  const save = useMutation({
    mutationFn: ({ name, area }: { name: string; area: SwitchArea['manual'] }) => put(`/api/switch-areas/${encodeURIComponent(name)}`, area),
    onSuccess: () => { setEditing(null); void qc.invalidateQueries({ queryKey: qk.switchAreas }) },
  })
  const d = query.data
  const blockLabel = Object.fromEntries((d?.blocks ?? []).map((b) => [b.id, b.label]))
  const todo = d?.switches.filter((s) => s.todo).length ?? 0
  const drift = d?.switches.filter((s) => s.drift.length).length ?? 0
  const serves = (s: SwitchArea) => [
    ...s.serves.blocks.map((b) => t('switchAreas.block', { block: blockLabel[b] ?? b })),
    ...(s.serves.rows.length ? [t('switchAreas.rows', { count: s.serves.rows.length })] : []),
    ...(s.serves.seats.length ? [t('switchAreas.seats', { count: s.serves.seats.length })] : []),
  ]
  return (
    <Layout title={t('switchAreas.title')}>
      <PageHead title={t('switchAreas.title')} desc={t('switchAreas.intro')} />
      <Stack gap="md">
        <ErrorBanner error={query.error ?? save.error} />
        {d && (todo > 0 || drift > 0) && (
          <Alert color="warn" role="status">
            {[todo ? t('switchAreas.todoCount', { count: todo }) : '', drift ? t('switchAreas.driftCount', { count: drift }) : '']
              .filter(Boolean).join(' ')}
          </Alert>
        )}
        <Card heading={2} padded={false}>
          {query.isPending ? <LoadingState rows={3} /> : !d?.switches.length ? (
            <EmptyState title={t('switchAreas.none')} description={t('switchAreas.noneHint')} />
          ) : (
            <Table.ScrollContainer minWidth={phone ? 0 : 720}>
              <Table verticalSpacing="sm" highlightOnHover className="bnb-table-stack">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('switchAreas.switch')}</Table.Th>
                    <Table.Th>{t('switchAreas.serves')}</Table.Th>
                    <Table.Th>{t('switchAreas.from')}</Table.Th>
                    <Table.Th>{t('switchAreas.check')}</Table.Th>
                    {canEdit && <Table.Th />}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {d.switches.map((s) => (
                    <Table.Tr key={s.id}>
                      <Table.Td className="bnb-stack-inline"><Text fw={600}>{s.name}</Text></Table.Td>
                      <Table.Td className="bnb-stack-inline">
                        <Group gap={4}>
                          {serves(s).map((x) => <Badge key={x} variant="light" color="gray" tt="none">{x}</Badge>)}
                          {!serves(s).length && <Text size="sm" c="dimmed">–</Text>}
                        </Group>
                      </Table.Td>
                      <Table.Td className="bnb-stack-inline"><Badge variant="light" color={HOW_COLOR[s.how]} tt="none">{t(`switchAreas.how.${s.how}`)}</Badge></Table.Td>
                      <Table.Td>
                        <Stack gap={4}>
                          {s.drift.map((x) => (
                            <Text key={x.kind} size="sm" c="warn">
                              {t(`switchAreas.drift.${x.kind}`, { seats: (x.seats ?? []).join(', '), block: x.block ?? '' })}
                            </Text>
                          ))}
                          {canEdit && s.suggest.map((r) => (
                            <Button key={r.id} size="compact-sm" variant="light" w="fit-content" loading={save.isPending}
                              onClick={() => save.mutate({ name: s.name, area: { ...s.manual, rows: [...s.manual.rows, r.id] } })}>
                              {t('switchAreas.pinRow', { row: `${r.block_label} ${r.name}` })}
                            </Button>
                          ))}
                          {!s.drift.length && !s.suggest.length && <Text size="sm" c="dimmed">{s.todo ? t('switchAreas.todo') : s.how === 'upstream' ? t('switchAreas.upstream') : t('switchAreas.agrees')}</Text>}
                        </Stack>
                      </Table.Td>
                      {canEdit && (
                        <Table.Td ta="right" className="bnb-stack-actions">
                          <Button size="compact-sm" variant="default" onClick={() => setEditing(s)}>{t('switchAreas.edit')}</Button>
                        </Table.Td>
                      )}
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Card>
      </Stack>
      {editing && d && (
        <AreaEditor sw={editing} blocks={d.blocks} saving={save.isPending} onClose={() => setEditing(null)}
          onSave={(area) => save.mutate({ name: editing.name, area })} />
      )}
    </Layout>
  )
}
