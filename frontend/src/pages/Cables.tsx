import {
  Alert, Autocomplete, Badge, Button, Group, Modal, NumberInput, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput,
} from '@mantine/core'
import { IconCloudDownload, IconDownload, IconLayoutRows, IconPlugConnected, IconPlus, IconPrinter, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { BlockPlan, Cable, CableImport, CableList } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { EntitySelect } from '@/components/EntitySelect'
import { PatchBlockModal } from '@/components/PatchBlockModal'
import { PatchCheck } from '@/components/PatchCheck'
import { PortClients } from '@/components/PortClients'
import { LoadingState, ErrorBanner } from '@/components/ui'

type Draft = Pick<Cable, 'label' | 'switch' | 'port' | 'panel' | 'panel_port' | 'seat' | 'color' | 'note'> & { length_m: number | string; type: string; speed: string }
const TYPES = ['cat5e', 'cat6', 'cat6a', 'fiber-sm', 'fiber-mm', 'dac']
const SPEEDS = ['1', '10', '25', '40', '100']

const EMPTY: Draft = { label: '', switch: '', port: '', panel: '', panel_port: '', seat: '', color: '', note: '', length_m: '', type: '', speed: '' }

function CableModal({ cable, all, canEdit, initial, onClose, onDone }: {
  cable: Cable | null; all: Cable[]; canEdit: boolean; initial?: Partial<Draft>; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const imported = cable?.source === 'import'
  const readOnly = !canEdit || imported
  const [d, setD] = useState<Draft>(() => cable
    ? { ...cable, length_m: cable.length_m ?? '', type: cable.type ?? '', speed: cable.speed ? String(cable.speed) : '' }
    : { ...EMPTY, ...initial })
  const set = (k: keyof Draft) => (v: string | number) => setD((x) => ({ ...x, [k]: v }))
  const text = (k: keyof Draft) => ({
    value: String(d[k]), readOnly,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k)(e.currentTarget.value),
  })
  const save = useMutation({
    mutationFn: () => {
      const body = { ...d, length_m: d.length_m === '' ? null : d.length_m, speed: d.speed ? Number(d.speed) : null }
      return cable ? patch<Cable>(`/api/cables/${cable.id}`, body) : post<Cable>('/api/cables', body)
    },
    onSuccess: onDone,
  })
  const remove = useMutation({ mutationFn: () => del(`/api/cables/${cable!.id}`), onSuccess: onDone })
  const uniq = (k: 'panel') => [...new Set(all.map((c) => c[k]).filter(Boolean))]
  return (
    <Modal opened onClose={onClose} title={cable ? cable.label : t('cables.add')} size="lg">
      <Stack gap="sm">
        {imported && <Alert color="info">{t('cables.fromImport', { plugin: cable?.plugin ?? 'NetBox' })}</Alert>}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <EntitySelect kind="switches" label={t('cables.switch')} required readOnly={readOnly}
            value={d.switch} onChange={(v) => setD((x) => ({ ...x, switch: v, port: v === x.switch ? x.port : '' }))} />
          <EntitySelect kind="ports" switchName={d.switch} label={t('cables.port')} required readOnly={readOnly}
            value={d.port} onChange={set('port')} />
          <Autocomplete label={t('cables.panel')} data={uniq('panel')} readOnly={readOnly}
            value={d.panel} onChange={set('panel')} placeholder={t('cables.panelPlaceholder')} />
          <TextInput label={t('cables.panelPort')} {...text('panel_port')} />
          <EntitySelect kind="seats" label={t('cables.seat')} readOnly={readOnly} value={d.seat} onChange={set('seat')} />
          <TextInput label={t('cables.label')} placeholder={t('cables.labelPlaceholder')} {...text('label')} />
          <TextInput label={t('cables.color')} {...text('color')} />
          <NumberInput label={t('cables.length')} min={0.1} max={500} step={0.5} decimalScale={1} readOnly={readOnly}
            value={d.length_m} onChange={set('length_m')} />
          <Select label={t('cables.type')} clearable readOnly={readOnly} value={d.type || null} onChange={(v) => set('type')(v ?? '')}
            data={TYPES.map((v) => ({ value: v, label: t(`topology.types.${v}`) }))} />
          <Select label={t('cables.speed')} clearable readOnly={readOnly} value={d.speed || null} onChange={(v) => set('speed')(v ?? '')}
            data={SPEEDS.map((v) => ({ value: v, label: `${v}G` }))} />
        </SimpleGrid>
        <TextInput label={t('cables.note')} maxLength={200} {...text('note')} />
        {(save.error || remove.error) && <Alert color="down" role="alert">{(save.error || remove.error)!.message}</Alert>}
        <Group justify="space-between">
          {cable ? (
            <Button variant="default" component="a" target="_blank" leftSection={<IconPrinter size={16} />}
              href={`/api/cables/labels.pdf?ids=${cable.id}`}>{t('cables.printOne')}</Button>
          ) : <span />}
          {!readOnly && (
            <Group gap="sm">
              {cable && <Button variant="subtle" color="down" loading={remove.isPending} onClick={() => remove.mutate()}>{t('cables.delete')}</Button>}
              <Button loading={save.isPending} disabled={!d.switch.trim() || !d.port.trim()} onClick={() => save.mutate()}>
                {t('cables.save')}
              </Button>
            </Group>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}

/** Which switch port goes to which patch panel port and seat, with labels for both ends (issue #97). */
export default function Cables() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const canEdit = useCan('floorplan.edit')
  const canSeeSeats = useCan('seats.view')
  const query = useQuery({ queryKey: qk.cables, queryFn: () => get<CableList>('/api/cables') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.cables })
  useLiveEvent('cables.changed', refresh)
  const [search, setSearch] = useState(params.get('q') ?? '')
  // A new cable, maybe started from a machine on an unexplained port (its switch and port filled in).
  const [adding, setAdding] = useState<Partial<Draft> | null>(null)
  const [patching, setPatching] = useState(false)
  const [patched, setPatched] = useState<BlockPlan | null>(null)
  const openId = params.get('cable')
  const close = () => { setAdding(null); if (openId) setParams({}, { replace: true }) }
  const doImport = useMutation({ mutationFn: () => post<CableImport>('/api/cables/import'), onSuccess: refresh })

  const d = query.data
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const rows = (d?.cables ?? []).filter((c) => {
    const hay = [c.label, c.switch, c.port, c.panel, c.panel_port, c.seat, c.color, c.note].join(' ').toLowerCase()
    return words.every((w) => hay.includes(w))
  })
  const current = d?.cables.find((c) => c.id === openId)
  const q = search.trim() ? `?q=${encodeURIComponent(search.trim())}` : ''

  return (
    <Layout title={t('cables.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('cables.title')} desc={t('cables.intro')}
        actions={
          <Group gap="xs">
            {canEdit && <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding({})}>{t('cables.add')}</Button>}
            {canEdit && <Button variant="default" leftSection={<IconLayoutRows size={16} />} onClick={() => setPatching(true)}>
              {t('cables.patchBlock')}</Button>}
            {canEdit && <Button variant="default" component="a" href="/cables/walk" leftSection={<IconPlugConnected size={16} />}>
              {t('walk.title')}</Button>}
            {canEdit && d && d.sources.length > 0 && (
              <Button variant="default" leftSection={<IconCloudDownload size={16} />} loading={doImport.isPending}
                onClick={() => doImport.mutate()}>{t('cables.import', { source: d.sources.join(', ') })}</Button>
            )}
            <Button variant="default" component="a" target="_blank" leftSection={<IconPrinter size={16} />}
              href={`/api/cables/labels.pdf${q}`}>{t('cables.labels')}</Button>
            <Button variant="default" component="a" leftSection={<IconDownload size={16} />}
              href={`/api/cables.csv${q}`}>CSV</Button>
          </Group>
        } />
      <Stack gap="md">
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {patched && (
          <Alert color="up" withCloseButton onClose={() => setPatched(null)}>
            {t('cables.created', { created: patched.created ?? 0, removed: patched.removed ?? 0 })}
          </Alert>
        )}
        {doImport.error && <Alert color="down" role="alert">{doImport.error.message}</Alert>}
        {doImport.data && (
          <Alert color={doImport.data.errors.length ? 'warn' : 'up'} withCloseButton onClose={() => doImport.reset()}>
            {t('cables.imported', { count: doImport.data.imported })}
            {doImport.data.errors.map((e) => <Text key={e} size="sm">{e}</Text>)}
          </Alert>
        )}
        <PatchCheck />
        {canSeeSeats && <PortClients canEdit={canEdit} onPatch={(c) => setAdding({ switch: c.switch, port: c.port, seat: c.ip_seat })} />}
        {query.isPending ? <LoadingState /> : d && (
          <>
            <TextInput leftSection={<IconSearch size={14} />} aria-label={t('cables.search')} placeholder={t('cables.search')}
              value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
            <Paper withBorder radius="lg" p="md">
              {rows.length === 0 ? <Text c="dimmed">{d.cables.length ? t('cables.noMatch') : t('cables.empty')}</Text> : (
                <Table.ScrollContainer minWidth={640}>
                  <Table striped highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>{t('cables.label')}</Table.Th><Table.Th>{t('cables.switchPort')}</Table.Th>
                        <Table.Th>{t('cables.panel')}</Table.Th><Table.Th>{t('cables.seat')}</Table.Th>
                        <Table.Th>{t('cables.cable')}</Table.Th><Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {rows.map((c) => (
                        <Table.Tr key={c.id}>
                          <Table.Td fw={600}>{c.label}</Table.Td>
                          <Table.Td ff="monospace">{c.switch} {c.port}</Table.Td>
                          <Table.Td>{c.panel ? `${c.panel} ${c.panel_port}`.trim() : <Text span c="dimmed">{t('cables.direct')}</Text>}</Table.Td>
                          <Table.Td>{c.seat || '–'}</Table.Td>
                          <Table.Td>
                            <Group gap={6} wrap="nowrap">
                              <Text size="sm">{[c.color, c.length_m ? `${c.length_m} m` : '', c.type ? t(`topology.types.${c.type}`) : '',
                                c.speed ? `${c.speed}G` : ''].filter(Boolean).join(' · ') || '–'}</Text>
                              {c.source === 'import' && <Badge variant="light" color="info" tt="none">{c.plugin ?? 'NetBox'}</Badge>}
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <Button size="compact-sm" variant="default" onClick={() => setParams({ cable: c.id })}>
                              {canEdit && c.source !== 'import' ? t('cables.edit') : t('cables.open')}
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </Paper>
            <Text size="sm" c="dimmed">{t('cables.count', { count: rows.length })}</Text>
          </>
        )}
      </Stack>
      {patching && d && (
        <PatchBlockModal
          onClose={() => setPatching(false)} onDone={(made) => { setPatching(false); setPatched(made); refresh() }} />
      )}
      {(adding || current) && d && (
        <CableModal key={current?.id ?? 'new'} cable={adding ? null : current ?? null} all={d.cables} canEdit={canEdit} initial={adding ?? undefined}
          onClose={close} onDone={() => { close(); refresh() }} />
      )}
    </Layout>
  )
}
