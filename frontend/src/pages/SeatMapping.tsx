import { Alert, Badge, Button, Group, Text, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconDownload, IconPlugConnected, IconPlus, IconUpload } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useSeatMap } from '@/api/queries'
import type { ResolvePortsResult, SeatRow } from '@/api/types'
import { ConfirmButton, DataTable, FilterBar, LoadingState, PageHead, useFilters } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { ImportDialog } from './seatmap/ImportDialog'
import { choices, matches } from './seatmap/model'
import { SeatForm, type SeatDraft } from './seatmap/SeatForm'

/** Where a row came from, in one compact cell (issue #872): the first source, "+n" for the rest,
 *  all of them in the tooltip, and the hand entry's note under it. */
function Sources({ row, label }: { row: SeatRow; label: (s: string) => string }) {
  const [first, ...rest] = row.sources
  if (!first) return <Text size="sm" c="dimmed">–</Text>
  return (
    <>
      <Tooltip label={row.sources.map(label).join(', ')} disabled={!rest.length}>
        <Group gap={4} wrap="nowrap" style={{ display: 'inline-flex' }}>
          <Badge size="sm" tt="none" variant={first === 'manual' ? 'filled' : 'light'} color={first === 'manual' ? 'bit' : 'gray'}>{label(first)}</Badge>
          {rest.length > 0 && <Text size="xs" c="dimmed" aria-label={row.sources.map(label).join(', ')}>+{rest.length}</Text>}
        </Group>
      </Tooltip>
      {row.manual?.note && <Text size="xs" c="dimmed">{row.manual.note}</Text>}
    </>
  )
}

function Cell({ value, source, label, mono }: { value: string; source?: string; label: (s: string) => string; mono?: boolean }) {
  if (!value) return <Text c="dimmed">–</Text>
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" ff={mono ? 'monospace' : undefined}>
        {value}
      </Text>
      {source === 'manual' && (
        <Tooltip label={label('manual')}>
          <Badge size="xs" variant="filled" color="bit" aria-label={label('manual')} style={{ flexShrink: 0 }}>
            ✎
          </Badge>
        </Tooltip>
      )}
      {source === 'network' && (
        <Tooltip label={label('network')}>
          <Badge size="xs" variant="light" color="gray" aria-label={label('network')} style={{ flexShrink: 0 }}>
            ⇄
          </Badge>
        </Tooltip>
      )}
    </Group>
  )
}

/** The key of the mapping: switch and port, and where they came from. */
function PortCell({ row }: { row: SeatRow }) {
  const { t } = useTranslation()
  if (!row.port) return <Text size="sm" c="dimmed">{t('seatmap.noPort')}</Text>
  const origin = row.port_origin ? t(`seatmap.origin.${row.port_origin}`) : ''
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" ff="monospace" style={{ whiteSpace: 'nowrap' }}>
        {row.switch} <b>{row.port}</b>
      </Text>
      {origin && (
        <Tooltip label={t(`seatmap.originLong.${row.port_origin}`)}>
          <Badge size="xs" variant={row.port_origin === 'manual' ? 'filled' : 'light'} color={row.port_origin === 'manual' ? 'bit' : 'gray'} tt="none" style={{ flexShrink: 0 }}>
            {origin}
          </Badge>
        </Tooltip>
      )}
    </Group>
  )
}

export default function SeatMapping() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const { data, error, isPending } = useSeatMap()
  // Techs see the mapping (seats.view) but only leads and admins change it (seats.edit).
  const canEdit = useCan('seats.edit')
  // ?q= from the floor plan's right-click menu ("Edit seat mapping", "Show in inventory")
  // The shared filter row like every other list, kept in the address (issue #1423).
  const filters = useFilters({ block: '', switch: '', source: '', show: 'all' })
  const query = filters.search
  const { block, switch: onSwitch, source, show } = filters.values
  const onlyManual = show === 'manual'
  const onlyOffPlan = show === 'offPlan'
  const [editing, setEditing] = useState<SeatRow | null>(null)
  const [formOpen, form] = useDisclosure(false)
  const [importOpen, importDialog] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  // Built-in sources by their name in the reader's language; plugins' sources as they call themselves.
  const label = (s: string) => (s === 'manual' ? t('seatmap.byHand') : t(`seatmap.sourceName.${s}`, { defaultValue: data?.labels[s] ?? s }))
  const refresh = () => client.invalidateQueries({ queryKey: qk.seatMap })

  const save = useMutation({
    mutationFn: (d: SeatDraft) =>
      put(`/api/seat-map/${encodeURIComponent(editing?.seat ?? d.seat.trim())}`, {
        switch: d.switch, port: d.port, ip: d.ip, mac: d.mac, nick: d.nick, note: d.note,
      }),
    onSuccess: () => {
      void refresh()
      form.close()
      setMessage({ ok: true, text: t('seatmap.saved') })
    },
    onError: (e) => setFormError(e.message),
  })
  const remove = useMutation({
    mutationFn: (seat: string) => del(`/api/seat-map/${encodeURIComponent(seat)}`),
    onSuccess: () => {
      void refresh()
      setMessage({ ok: true, text: t('seatmap.removed') })
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  // Hand entries from before the port was the key: offer to look their port up once.
  const portless = (data?.seats ?? []).filter((r) => r.manual && !r.manual.switch && (r.manual.ip || r.manual.mac)).length
  const resolve = useMutation({
    mutationFn: () => post<ResolvePortsResult>('/api/seat-map/resolve-ports', {}),
    onSuccess: (r) => {
      void refresh()
      setMessage({ ok: true, text: t('seatmap.resolved', { found: Object.keys(r.found).length, missed: r.missed.length, taken: r.taken.length }) })
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  const all = data?.seats ?? []
  const rows = all.filter((r) => matches(r, query, onlyManual, onlyOffPlan, { block, switch: onSwitch, source }))
  const blocks = choices(all.map((r) => r.block ?? ''))
  const switches = choices(all.map((r) => r.switch))
  const sourceIds = choices(all.flatMap((r) => r.sources))
  // Seats a source names that no seat block has (a stale seats.json, a typo in a CSV): counted apart,
  // so the total here matches the plan and the dashboards.
  const offPlan = (data?.seats ?? []).filter((r) => r.on_plan === false).length
  const errors = Object.entries(data?.errors ?? {})

  function open(row: SeatRow | null) {
    setEditing(row)
    setFormError(null)
    form.open()
  }

  return (
    <Layout title={t('seatmap.title')} back={{ href: '/', label: t('common.floorPlan') }} fill>
      <PageHead
        title={t('seatmap.title')}
        desc={t('seatmap.intro')}
        actions={canEdit && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => open(null)}>
            {t('seatmap.add')}
          </Button>
        )}
        // One primary action; export and import behind "⋯" so a phone shows them whole (#1044).
        menu={[
          { label: t('seatmap.export'), icon: <IconDownload size={16} aria-hidden="true" />, href: '/api/seat-map.csv', download: true },
          ...(canEdit ? [{ label: t('seatmap.import'), icon: <IconUpload size={16} aria-hidden="true" />, onClick: importDialog.open }] : []),
        ]}
      />
      {errors.length > 0 && (
        <Alert color="warn" mb="md" role="alert">
          {t('seatmap.sourceErrors', { errors: errors.map(([s, e]) => `${label(s)}: ${e}`).join('; ') })}
        </Alert>
      )}
      <Text size="sm" role="status" mb="sm" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {message ? `${message.ok ? '✓' : '✕'} ${message.text}` : ''}
      </Text>
      <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('seatmap.searchPlaceholder')} onClear={filters.clear}
        groups={filters.groups([
          { key: 'block', label: t('seatmap.block'), hidden: blocks.length < 2,
            options: [{ value: '', label: t('seatmap.any') }, ...blocks.map((v) => ({ value: v, label: v }))] },
          { key: 'switch', label: t('seatmap.switch'), hidden: switches.length < 2,
            options: [{ value: '', label: t('seatmap.any') }, ...switches.map((v) => ({ value: v, label: v }))] },
          { key: 'source', label: t('seatmap.source'), hidden: sourceIds.length < 2,
            options: [{ value: '', label: t('seatmap.any') }, ...sourceIds.map((v) => ({ value: v, label: label(v) }))] },
          { key: 'show', label: t('listFilters.show'), options: [
            { value: 'all', label: t('listFilters.all'), count: all.length },
            { value: 'manual', label: t('seatmap.onlyManual'), count: all.filter((r) => r.manual).length },
            ...(offPlan > 0 || onlyOffPlan ? [{ value: 'offPlan', label: t('seatmap.onlyOffPlan'), count: offPlan }] : []),
          ] },
        ])}
        actions={canEdit && portless > 0 && (
          <Button variant="light" leftSection={<IconPlugConnected size={16} />} loading={resolve.isPending} onClick={() => resolve.mutate()}>
            {t('seatmap.resolve', { count: portless })}
          </Button>
        )} />
      {isPending && <LoadingState rows={3} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && (
        <>
          <Text size="sm" c="dimmed" mb="xs">
            {offPlan > 0 && rows.length === data.seats.length
              ? t('seatmap.countSplit', { count: rows.length, onPlan: rows.length - offPlan, off: offPlan })
              : t('seatmap.count', { count: rows.length })}
          </Text>
          <DataTable fill label={t('seatmap.title')} rows={rows} rowKey={(r) => r.seat} defaultSort={{ id: 'seat' }} cards
            empty={<Text>{data.seats.length ? t('seatmap.noMatch') : t('seatmap.empty')}</Text>}
            columns={[
              { id: 'seat', header: t('seatmap.seat'), sort: (r) => r.seat, cell: (r) => (<>{canEdit
                ? <Button variant="subtle" size="compact-sm" onClick={() => open(r)} ff="monospace">{r.seat}</Button>
                : <Text size="sm" ff="monospace" fw={600} span>{r.seat}</Text>}{r.on_plan === false && (
                  <Badge size="xs" variant="light" color="gray" ml={4} title={t('seatmap.offPlanHint')}>{t('seatmap.offPlan')}</Badge>
                )}</>) },
              { id: 'port', header: t('seatmap.port'), card: 'label', sort: (r) => `${r.switch} ${r.port}`, cell: (r) => <PortCell row={r} /> },
              { id: 'nick', header: t('seatmap.nick'), card: 'label', sort: (r) => r.nick, cell: (r) => <Cell value={r.nick} source={r.from.nick} label={label} /> },
              { id: 'ip', header: t('seatmap.ip'), card: 'label', sort: (r) => r.ip, cell: (r) => <Cell value={r.ip} source={r.from.ip} label={label} mono /> },
              { id: 'mac', header: t('seatmap.mac'), card: 'label', sort: (r) => r.mac, cell: (r) => <Cell value={r.mac} source={r.from.mac} label={label} mono /> },
              { id: 'from', header: t('seatmap.from'), card: 'label', sort: (r) => r.sources.map(label).join(', '), cell: (r) => <Sources row={r} label={label} /> },
              { id: 'actions', header: null, card: 'actions', cell: (r) => canEdit && r.manual && (
                <ConfirmButton size="xs" variant="subtle" danger label={t('seatmap.removeManual')}
                  question={t('seatmap.removeQuestion', { seat: r.seat })} onConfirm={() => remove.mutate(r.seat)} />
              ) },
            ]} />
        </>
      )}
      {formOpen && (
        <SeatForm
          key={editing?.seat ?? 'new'}
          row={editing}
          label={label}
          opened={formOpen}
          busy={save.isPending}
          error={formError}
          onClose={form.close}
          onSave={(d) => save.mutate(d)}
        />
      )}
      {importOpen && (
        <ImportDialog
          opened={importOpen}
          onClose={importDialog.close}
          onDone={(r) => {
            importDialog.close()
            void refresh()
            setMessage({ ok: true, text: t('seatmap.imported', { ...r }) })
          }}
        />
      )}
    </Layout>
  )
}
