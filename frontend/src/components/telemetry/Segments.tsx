import { Alert, Badge, Button, Group, NumberInput, Stack, Switch, Table, Text, TextInput } from '@mantine/core'
import { IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { ConfirmIcon } from '@/components/ConfirmButton'
import { EmptyState, Panel } from '@/components/ui'

export interface Segment {
  id: string
  vlan: number
  network: string
  name: string
  lookups: boolean
  source: 'discovery' | 'manual'
  device?: string
}

interface SegmentList {
  segments: Segment[]
  proposals: { vlan: number; network: string; name: string; device: string }[]
}

const KEY = ['settings-segments'] as const

/** Network segments (a VLAN and its IP range) and whether check-ins may look PCs up in them
 *  (issue #946, docs/segments.md). Every segment starts with lookups off. */
export function Segments() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const list = useQuery({ queryKey: KEY, queryFn: () => get<SegmentList>('/api/settings/segments') })
  const refresh = () => qc.invalidateQueries({ queryKey: KEY })
  const discover = useMutation({ mutationFn: () => post<{ added: number; updated: number }>('/api/settings/segments/discover'), onSuccess: refresh })
  const change = useMutation({ mutationFn: ({ id, body }: { id: string; body: Partial<Segment> }) => patch(`/api/settings/segments/${id}`, body), onSuccess: refresh })
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/settings/segments/${id}`), onSuccess: refresh })
  const segments = list.data?.segments ?? []
  const known = new Set(segments.map((s) => s.network))
  const waiting = (list.data?.proposals ?? []).filter((p) => !known.has(p.network)).length
  const on = segments.filter((s) => s.lookups).length
  const error = list.error ?? discover.error ?? change.error ?? remove.error

  return (
    <Stack gap="md">
      <Panel title={t('segments.title')} desc={t('segments.intro')}
        actions={<Button variant="default" loading={discover.isPending} onClick={() => discover.mutate()}>
          {waiting ? t('segments.takeDiscovered', { count: waiting }) : t('segments.discover')}</Button>}>
        <Stack gap="sm">
          {error && <Alert color="down" role="alert">{error.message}</Alert>}
          {discover.data && (
            <Alert color="up" role="status" withCloseButton onClose={() => discover.reset()}>
              {t('segments.discovered', { added: discover.data.added, updated: discover.data.updated })}
            </Alert>
          )}
          {segments.length > 0 && on === 0 && <Alert color="warn" role="status">{t('segments.noneOn')}</Alert>}
          {segments.length === 0 && !list.isLoading
            ? <EmptyState title={t('segments.empty')} desc={t('segments.emptyDesc')} />
            : (
              <Table verticalSpacing="xs" className="fb-table-stack">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('segments.vlan')}</Table.Th>
                    <Table.Th>{t('segments.network')}</Table.Th>
                    <Table.Th>{t('segments.name')}</Table.Th>
                    <Table.Th>{t('segments.source')}</Table.Th>
                    <Table.Th>{t('segments.lookups')}</Table.Th>
                    <Table.Th aria-label={t('segments.actions')} />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {segments.map((s) => (
                    <Table.Tr key={s.id}>
                      <Table.Td data-label={t('segments.vlan')}>{s.vlan}</Table.Td>
                      <Table.Td data-label={t('segments.network')}><Text ff="monospace" size="sm">{s.network}</Text></Table.Td>
                      <Table.Td data-label={t('segments.name')}>{s.name || '–'}</Table.Td>
                      <Table.Td data-label={t('segments.source')}>
                        <Badge variant="light" color="gray" tt="none">
                          {s.source === 'discovery' ? t('segments.fromDiscovery', { device: s.device || '?' }) : t('segments.byHand')}
                        </Badge>
                      </Table.Td>
                      <Table.Td data-label={t('segments.lookups')}>
                        <Switch aria-label={t('segments.lookupsFor', { vlan: s.vlan })} checked={s.lookups}
                          disabled={change.isPending} onChange={(e) => change.mutate({ id: s.id, body: { lookups: e.currentTarget.checked } })} />
                      </Table.Td>
                      <Table.Td className="fb-stack-actions">
                        <ConfirmIcon label={t('segments.remove', { vlan: s.vlan })} onConfirm={() => remove.mutate(s.id)}>
                          <IconTrash size={16} />
                        </ConfirmIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
        </Stack>
      </Panel>
      <AddSegment onAdded={refresh} />
    </Stack>
  )
}

function AddSegment({ onAdded }: { onAdded: () => void }) {
  const { t } = useTranslation()
  const [vlan, setVlan] = useState<string | number>('')
  const [network, setNetwork] = useState('')
  const [name, setName] = useState('')
  const add = useMutation({
    mutationFn: () => post('/api/settings/segments', { vlan, network, name }),
    onSuccess: () => { setVlan(''); setNetwork(''); setName(''); onAdded() },
  })
  return (
    <Panel title={t('segments.addTitle')} desc={t('segments.addDesc')}>
      <Stack gap="sm">
        {add.error && <Alert color="down" role="alert">{add.error.message}</Alert>}
        <Group align="flex-end" gap="sm">
          <NumberInput label={t('segments.vlan')} min={1} max={4094} value={vlan} onChange={setVlan} w={120} />
          <TextInput label={t('segments.network')} placeholder="10.10.0.0/22" value={network}
            onChange={(e) => setNetwork(e.currentTarget.value)} w={200} />
          <TextInput label={t('segments.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} w={220} />
          <Button loading={add.isPending} disabled={!vlan || !network.trim()} onClick={() => add.mutate()}>{t('segments.add')}</Button>
        </Group>
      </Stack>
    </Panel>
  )
}
