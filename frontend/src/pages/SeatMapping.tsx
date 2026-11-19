import { Alert, Badge, Button, Group, Paper, Switch, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconDownload, IconPlugConnected, IconPlus, IconSearch, IconUpload } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useSeatMap } from '@/api/queries'
import type { ResolvePortsResult, SeatRow } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ImportDialog } from './seatmap/ImportDialog'
import { matches } from './seatmap/model'
import { SeatForm, type SeatDraft } from './seatmap/SeatForm'
import { LoadingState } from '@/components/ui'

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
          <Badge size="xs" variant="light" color="trace" aria-label={label('network')} style={{ flexShrink: 0 }}>
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
          <Badge size="xs" variant={row.port_origin === 'manual' ? 'filled' : 'light'} color={row.port_origin === 'manual' ? 'bit' : 'trace'} tt="none" style={{ flexShrink: 0 }}>
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
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('q') ?? '')
  const [onlyManual, setOnlyManual] = useState(false)
  const [onlyOffPlan, setOnlyOffPlan] = useState(false)
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

  const rows = (data?.seats ?? []).filter((r) => matches(r, query, onlyManual, onlyOffPlan))
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
    <Layout title={t('seatmap.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('seatmap.title')}
        desc={t('seatmap.intro')}
        actions={
          <>
            <Button component="a" href="/api/seat-map.csv" variant="default" leftSection={<IconDownload size={16} />}>
              {t('seatmap.export')}
            </Button>
            {canEdit && (
              <>
                <Button variant="default" leftSection={<IconUpload size={16} />} onClick={importDialog.open}>
                  {t('seatmap.import')}
                </Button>
                <Button leftSection={<IconPlus size={16} />} onClick={() => open(null)}>
                  {t('seatmap.add')}
                </Button>
              </>
            )}
          </>
        }
      />
      {errors.length > 0 && (
        <Alert color="warn" mb="md" role="alert">
          {t('seatmap.sourceErrors', { errors: errors.map(([s, e]) => `${label(s)}: ${e}`).join('; ') })}
        </Alert>
      )}
      <Text size="sm" role="status" mb="sm" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {message ? `${message.ok ? '✓' : '✕'} ${message.text}` : ''}
      </Text>
      <Group gap="sm" mb="md" align="flex-end" wrap="wrap">
        <TextInput
          label={t('seatmap.search')}
          placeholder={t('seatmap.searchPlaceholder')}
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          style={{ flex: '1 1 260px' }}
        />
        <Switch label={t('seatmap.onlyManual')} checked={onlyManual} onChange={(e) => setOnlyManual(e.currentTarget.checked)} mb={8} />
        {(offPlan > 0 || onlyOffPlan) && (
          <Switch label={t('seatmap.onlyOffPlan')} checked={onlyOffPlan} onChange={(e) => setOnlyOffPlan(e.currentTarget.checked)} mb={8} />
        )}
        {canEdit && portless > 0 && (
          <Button variant="light" leftSection={<IconPlugConnected size={16} />} loading={resolve.isPending} onClick={() => resolve.mutate()}>
            {t('seatmap.resolve', { count: portless })}
          </Button>
        )}
      </Group>
      {isPending && <LoadingState />}
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
          {rows.length === 0 ? (
            <Text>{data.seats.length ? t('seatmap.noMatch') : t('seatmap.empty')}</Text>
          ) : (
            <Paper withBorder radius="lg" px={{ base: 'sm', sm: 0 }}>
                <Table highlightOnHover verticalSpacing="xs" fz="sm" className="fb-table-stack">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('seatmap.seat')}</Table.Th>
                      <Table.Th>{t('seatmap.port')}</Table.Th>
                      <Table.Th>{t('seatmap.nick')}</Table.Th>
                      <Table.Th>{t('seatmap.ip')}</Table.Th>
                      <Table.Th>{t('seatmap.mac')}</Table.Th>
                      <Table.Th>{t('seatmap.from')}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {rows.map((r) => (
                      <Table.Tr key={r.seat}>
                        <Table.Td>
                          {canEdit ? (
                            <Button variant="subtle" size="compact-sm" onClick={() => open(r)} ff="monospace">
                              {r.seat}
                            </Button>
                          ) : (
                            <Text size="sm" ff="monospace" fw={600}>
                              {r.seat}
                            </Text>
                          )}
                          {r.on_plan === false && (
                            <Badge size="xs" variant="light" color="gray" ml={4} title={t('seatmap.offPlanHint')}>
                              {t('seatmap.offPlan')}
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td data-label={t('seatmap.port')}>
                          <PortCell row={r} />
                        </Table.Td>
                        <Table.Td data-label={t('seatmap.nick')} style={{ whiteSpace: 'nowrap' }}>
                          <Cell value={r.nick} source={r.from.nick} label={label} />
                        </Table.Td>
                        <Table.Td data-label={t('seatmap.ip')}>
                          <Cell value={r.ip} source={r.from.ip} label={label} mono />
                        </Table.Td>
                        <Table.Td data-label={t('seatmap.mac')}>
                          <Cell value={r.mac} source={r.from.mac} label={label} mono />
                        </Table.Td>
                        <Table.Td data-label={t('seatmap.from')}>
                          <Group gap={4}>
                            {r.sources.map((s) => (
                              <Badge key={s} size="sm" tt="none" variant={s === 'manual' ? 'filled' : 'light'} color={s === 'manual' ? 'bit' : 'trace'}>
                                {label(s)}
                              </Badge>
                            ))}
                          </Group>
                          {r.manual?.note && (
                            <Text size="xs" c="dimmed">
                              {r.manual.note}
                            </Text>
                          )}
                        </Table.Td>
                        <Table.Td className="fb-stack-actions">
                          {canEdit && r.manual && (
                            <ConfirmButton
                              size="xs"
                              variant="subtle"
                              danger
                              label={t('seatmap.removeManual')}
                              question={t('seatmap.removeQuestion', { seat: r.seat })}
                              onConfirm={() => remove.mutate(r.seat)}
                            />
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
            </Paper>
          )}
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
