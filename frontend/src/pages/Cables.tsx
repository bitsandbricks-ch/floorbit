import {
  Alert, Anchor, Badge, Button, Group, Menu, Stack, Text, TextInput,
} from '@mantine/core'
import { IconChevronDown, IconCloudDownload, IconDownload, IconLayoutRows, IconPlugConnected, IconPlus, IconPrinter, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { BlockPlan, CableImport, CableList } from '@/api/types'
import { DataTable } from '@/components/DataTable'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { PatchBlockModal } from '@/components/PatchBlockModal'
import { PatchCheck } from '@/components/PatchCheck'
import { PortAreas } from '@/components/PortAreas'
import { PortClients } from '@/components/PortClients'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'

/** Which switch port goes to which patch panel port and seat, with labels for both ends (issue #97). */
export default function Cables() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const canEdit = useCan('floorplan.edit')
  const canSeeSeats = useCan('seats.view')
  const query = useQuery({ queryKey: qk.cables, queryFn: () => get<CableList>('/api/cables') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.cables })
  // Port areas still pick from the switch list; the cable form uses EntitySelect.
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches'),
    enabled: canEdit })
  useLiveEvent('cables.changed', refresh)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const [patching, setPatching] = useState(false)
  const [patched, setPatched] = useState<BlockPlan | null>(null)
  const doImport = useMutation({ mutationFn: () => post<CableImport>('/api/cables/import'), onSuccess: refresh })

  const d = query.data
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const rows = (d?.cables ?? []).filter((c) => {
    const hay = [c.label, c.switch, c.port, c.panel, c.panel_port, c.seat, c.color, c.note].join(' ').toLowerCase()
    return words.every((w) => hay.includes(w))
  })
  const q = search.trim() ? `?q=${encodeURIComponent(search.trim())}` : ''

  return (
    <Layout title={t('cables.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('cables.title')} desc={t('cables.intro')}
        actions={
          <Group gap="xs">
            {canEdit && <Button leftSection={<IconPlus size={16} />} component={Link} to="/cables/new">{t('cables.add')}</Button>}
            {canEdit && <Button variant="default" component="a" href="/cables/walk" leftSection={<IconPlugConnected size={16} />}>
              {t('walk.title')}</Button>}
            {/* The rest in a menu: six buttons pushed the bar past a laptop screen. */}
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <Button variant="default" rightSection={<IconChevronDown size={14} />}>{t('cables.more')}</Button>
              </Menu.Target>
              <Menu.Dropdown>
                {canEdit && <Menu.Item leftSection={<IconLayoutRows size={14} />} onClick={() => setPatching(true)}>{t('cables.patchBlock')}</Menu.Item>}
                {canEdit && d && d.sources.length > 0 && (
                  <Menu.Item leftSection={<IconCloudDownload size={14} />} disabled={doImport.isPending} onClick={() => doImport.mutate()}>
                    {t('cables.import', { source: d.sources.join(', ') })}
                  </Menu.Item>
                )}
                <Menu.Item component="a" target="_blank" href={`/api/cables/labels.pdf${q}`} leftSection={<IconPrinter size={14} />}>
                  {t('cables.labels')}</Menu.Item>
                <Menu.Item component="a" href={`/api/cables.csv${q}`} leftSection={<IconDownload size={14} />}>CSV</Menu.Item>
              </Menu.Dropdown>
            </Menu>
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
        {canSeeSeats && <PortClients canEdit={canEdit} onPatch={(c) => navigate(`/cables/new?${new URLSearchParams({ switch: c.switch, port: c.port, seat: c.ip_seat })}`)} />}
        {query.isPending ? <LoadingState rows={3} /> : d && (
          <>
            <TextInput leftSection={<IconSearch size={14} />} aria-label={t('cables.search')} placeholder={t('cables.search')}
              value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
            <DataTable label={t('cables.title')} rows={rows} rowKey={(c) => c.id} defaultSort={{ id: 'label' }} minWidth={640}
              empty={<Text c="dimmed">{d.cables.length ? t('cables.noMatch') : t('cables.empty')}</Text>}
              count={(n) => t('cables.count', { count: n })}
              columns={[
                { id: 'label', header: t('cables.label'), sort: (c) => c.label, cell: (c) => <Anchor component={Link} to={`/cables/${c.id}`} fw={600}>{c.label}</Anchor> },
                { id: 'port', header: t('cables.switchPort'), sort: (c) => `${c.switch} ${c.port}`, cell: (c) => `${c.switch} ${c.port}`, mono: true },
                { id: 'panel', header: t('cables.panel'), sort: (c) => (c.panel ? `${c.panel} ${c.panel_port}` : ''), hideOnPhone: true,
                  cell: (c) => (c.panel ? `${c.panel} ${c.panel_port}`.trim() : <Text span c="dimmed">{t('cables.direct')}</Text>) },
                { id: 'seat', header: t('cables.seat'), sort: (c) => c.seat ?? '', cell: (c) => c.seat || '–' },
                { id: 'cable', header: t('cables.cable'), hideOnPhone: true, cell: (c) => (
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm">{[c.color, c.length_m ? `${c.length_m} m` : '', c.type ? t(`topology.types.${c.type}`) : '',
                      c.speed ? `${c.speed}G` : ''].filter(Boolean).join(' · ') || '–'}</Text>
                    {c.source === 'import' && <Badge variant="light" color="info" tt="none">{c.plugin ?? 'NetBox'}</Badge>}
                  </Group>
                ) },
              ]} />
          </>
        )}
      </Stack>
      {patching && d && (
        <PatchBlockModal
          onClose={() => setPatching(false)} onDone={(made) => { setPatching(false); setPatched(made); refresh() }} />
      )}
    </Layout>
  )
}
