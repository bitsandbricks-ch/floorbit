import {
  Alert, Badge, Button, Group, Paper, Stack, Table, Text, TextInput,
} from '@mantine/core'
import { IconCloudDownload, IconDownload, IconLayoutRows, IconPlugConnected, IconPlus, IconPrinter, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { BlockPlan, CableImport, CableList } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { CableModal, type CableDraft } from '@/components/CableModal'
import { PatchBlockModal } from '@/components/PatchBlockModal'
import { PatchCheck } from '@/components/PatchCheck'
import { PortAreas } from '@/components/PortAreas'
import { PortClients } from '@/components/PortClients'
import { LoadingState, ErrorBanner } from '@/components/ui'

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
  const [adding, setAdding] = useState<Partial<CableDraft> | null>(null)
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
        <PortAreas canEdit={canEdit}
          switches={[...new Set([...(switches.data ?? []).map((s) => s.name), ...(d?.cables ?? []).map((c) => c.switch)])].sort()} />
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
        <CableModal key={current?.id ?? 'new'} cable={adding ? null : current ?? null} canEdit={canEdit} initial={adding ?? undefined}
          onClose={close} onDone={() => { close(); refresh() }} />
      )}
    </Layout>
  )
}
