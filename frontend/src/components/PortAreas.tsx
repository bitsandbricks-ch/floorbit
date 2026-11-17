import { ActionIcon, Alert, Autocomplete, Button, Group, Modal, NumberInput, Paper, SimpleGrid, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { PortArea } from '@/api/types'

type Draft = Omit<PortArea, 'id' | 'label'>

/** Rough port areas (floorbit/port_areas.py): "ports 1-10 go to A-1..A-10", per switch. The crew
 *  knows the layout in batches long before it knows each seat's port. */
export function PortAreas({ canEdit, switches }: { canEdit: boolean; switches: string[] }) {
  const { t } = useTranslation()
  const query = useQuery({ queryKey: qk.portAreas, queryFn: () => get<{ areas: PortArea[] }>('/api/port-areas') })
  const [editing, setEditing] = useState<string | null>(null)   // '' for a new switch
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/port-areas/${id}`), onSuccess: () => void query.refetch() })
  const areas = query.data?.areas ?? []
  const bySwitch = [...new Set(areas.map((a) => a.switch))]
  if (!canEdit && !areas.length) return null
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb="xs" wrap="wrap">
        <div>
          <Title order={3} size="h5">{t('cables.areasTitle')}</Title>
          <Text size="sm" c="dimmed">{t('cables.areasIntro')}</Text>
        </div>
        {canEdit && <Button variant="default" onClick={() => setEditing('')}>{t('cables.areasAdd')}</Button>}
      </Group>
      {remove.error && <Alert color="down" role="alert" mb="xs">{remove.error.message}</Alert>}
      {bySwitch.length === 0 ? <Text size="sm" c="dimmed">{t('cables.areasEmpty')}</Text> : (
        <Table.ScrollContainer minWidth={420}>
          <Table>
            <Table.Tbody>
              {bySwitch.map((sw) => (
                <Table.Tr key={sw}>
                  <Table.Td ff="monospace" fw={600} w={160}>{sw}</Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="wrap">
                      {areas.filter((a) => a.switch === sw).map((a) => (
                        <Group key={a.id} gap={2} wrap="nowrap" style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 8, padding: '2px 4px 2px 8px' }}>
                          <Text size="sm">{t('cables.areaRange', { first: a.first, last: a.last, label: a.label })}</Text>
                          {canEdit && (
                            <Tooltip label={t('cables.areaRemove')}>
                              <ActionIcon size="sm" variant="subtle" color="down" aria-label={t('cables.areaRemoveOne', { label: a.label })}
                                onClick={() => remove.mutate(a.id)}><IconTrash size={14} /></ActionIcon>
                            </Tooltip>
                          )}
                        </Group>
                      ))}
                    </Group>
                  </Table.Td>
                  {canEdit && <Table.Td w={90}><Button size="compact-sm" variant="default" onClick={() => setEditing(sw)}>{t('cables.edit')}</Button></Table.Td>}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {editing !== null && (
        <PortAreasModal switches={switches} initial={editing} existing={areas.filter((a) => a.switch === editing)}
          onClose={() => setEditing(null)} onDone={() => { setEditing(null); void query.refetch() }} />
      )}
    </Paper>
  )
}

function PortAreasModal({ switches, initial, existing, onClose, onDone }: {
  switches: string[]; initial: string; existing: PortArea[]; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const firstSize = existing.length ? existing[0].last - existing[0].first + 1 : 10
  const [sw, setSw] = useState(initial)
  const [size, setSize] = useState<number>(firstSize)
  const [batches, setBatches] = useState<number>(existing.length ? Math.max(...existing.map((a) => Math.round((a.last - (existing[0].first - 1)) / firstSize))) : 4)
  const [firstPort, setFirstPort] = useState<number>(existing.length ? Math.min(...existing.map((a) => a.first)) : 1)
  const [starts, setStarts] = useState<string[]>(() => {
    const out: string[] = []
    for (const a of existing) out[Math.round((a.first - (existing[0].first)) / firstSize)] = a.seats[0]
    return out
  })
  const list = Array.from({ length: Math.max(1, Math.min(12, batches || 1)) }, (_, i) => starts[i] ?? '')
  const body = { switch: sw.trim(), size, first_port: firstPort, starts: list }
  const [typed] = useDebouncedValue(body, 300)
  const ready = Boolean(typed.switch && typed.starts.some((s) => s.trim()))
  const preview = useQuery({
    queryKey: qk.portAreasPreview(typed),
    queryFn: () => post<{ areas: Draft[] }>('/api/port-areas/batch', { ...typed, dry_run: true }),
    enabled: ready, retry: false,
  })
  const save = useMutation({ mutationFn: () => post('/api/port-areas/batch', body), onSuccess: onDone })
  return (
    <Modal opened onClose={onClose} title={t('cables.areasTitle')} size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('cables.areasHow')}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Autocomplete label={t('cables.switch')} required data={switches} value={sw} onChange={setSw} />
          <NumberInput label={t('cables.areasSize')} min={1} max={64} value={size} onChange={(v) => setSize(Number(v) || 1)} />
          <NumberInput label={t('cables.areasFirstPort')} min={0} max={128} value={firstPort} onChange={(v) => setFirstPort(Number(v) || 0)} />
          <NumberInput label={t('cables.areasBatches')} min={1} max={12} value={batches} onChange={(v) => setBatches(Number(v) || 1)} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
          {list.map((s, i) => (
            <TextInput key={i} placeholder={t('cables.areasSkip')} value={s}
              label={t('cables.areasBatch', { first: firstPort + i * size, last: firstPort + (i + 1) * size - 1 })}
              onChange={(e) => { const v = e.currentTarget.value; setStarts((cur) => { const n = [...cur]; n[i] = v; return n }) }} />
          ))}
        </SimpleGrid>
        {preview.error && <Alert color="down" role="alert">{preview.error.message}</Alert>}
        {preview.data && !preview.error && (
          <Text size="sm">{preview.data.areas.map((a) => t('cables.areaRange', { first: a.first, last: a.last, label: `${a.seats[0]}..${a.seats[a.seats.length - 1]}` })).join(' · ')}</Text>
        )}
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={!ready || !!preview.error} loading={save.isPending} onClick={() => save.mutate()}>{t('cables.areasSave')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
