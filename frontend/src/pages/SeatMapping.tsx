import { Alert, Badge, Button, Group, Loader, Paper, Switch, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconDownload, IconPlus, IconSearch, IconUpload } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useSeatMap } from '@/api/queries'
import type { SeatRow } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ImportDialog } from './seatmap/ImportDialog'
import { matches } from './seatmap/model'
import { SeatForm, type SeatDraft } from './seatmap/SeatForm'

function Cell({ value, source, label, mono }: { value: string; source?: string; label: (s: string) => string; mono?: boolean }) {
  if (!value) return <Text c="dimmed">–</Text>
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" ff={mono ? 'monospace' : undefined}>
        {value}
      </Text>
      {source === 'manual' && (
        <Tooltip label={label('manual')}>
          <Badge size="xs" variant="filled" color="bit" aria-label={label('manual')}>
            ✎
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
  const [query, setQuery] = useState('')
  const [onlyManual, setOnlyManual] = useState(false)
  const [editing, setEditing] = useState<SeatRow | null>(null)
  const [formOpen, form] = useDisclosure(false)
  const [importOpen, importDialog] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const label = (s: string) => (s === 'manual' ? t('seatmap.byHand') : (data?.labels[s] ?? s))
  const refresh = () => client.invalidateQueries({ queryKey: qk.seatMap })

  const save = useMutation({
    mutationFn: (d: SeatDraft) =>
      put(`/api/seat-map/${encodeURIComponent(editing?.seat ?? d.seat.trim())}`, { ip: d.ip, mac: d.mac, nick: d.nick, note: d.note }),
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

  const rows = (data?.seats ?? []).filter((r) => matches(r, query, onlyManual))
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
            <Button variant="default" leftSection={<IconUpload size={16} />} onClick={importDialog.open}>
              {t('seatmap.import')}
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => open(null)}>
              {t('seatmap.add')}
            </Button>
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
      </Group>
      {isPending && <Loader aria-label={t('common.loading')} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && (
        <>
          <Text size="sm" c="dimmed" mb="xs">
            {t('seatmap.count', { count: rows.length })}
          </Text>
          {rows.length === 0 ? (
            <Text>{data.seats.length ? t('seatmap.noMatch') : t('seatmap.empty')}</Text>
          ) : (
            <Paper withBorder radius="lg">
              <Table.ScrollContainer minWidth={720}>
                <Table highlightOnHover verticalSpacing="xs" fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{t('seatmap.seat')}</Table.Th>
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
                          <Button variant="subtle" size="compact-sm" onClick={() => open(r)} ff="monospace">
                            {r.seat}
                          </Button>
                        </Table.Td>
                        <Table.Td>
                          <Cell value={r.nick} source={r.from.nick} label={label} />
                        </Table.Td>
                        <Table.Td>
                          <Cell value={r.ip} source={r.from.ip} label={label} mono />
                        </Table.Td>
                        <Table.Td>
                          <Cell value={r.mac} source={r.from.mac} label={label} mono />
                        </Table.Td>
                        <Table.Td>
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
                        <Table.Td>
                          {r.manual && (
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
              </Table.ScrollContainer>
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
