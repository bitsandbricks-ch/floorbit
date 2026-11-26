import { Alert, Button, Group, Paper, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  WINDOWS, downloadFlows, searchFlows, type FlowLookupAnswer, type FlowQuery, type FlowRow, type FlowWindow,
} from '@/api/flowLookup'
import { DataTable, EmptyState, ErrorBanner, PageHead, type DataColumn } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { dayClock } from '@/lib/time'
import { bytes } from './traffic/format'

const REASON_MIN = 5

function side(ip: string, seat: string | null) {
  return seat ? `${seat} · ${ip}` : ip
}

/** Traffic › Flow lookup (#1481, C): the raw flows the agents keep, for an incident. Needs
 *  traffic.investigate and a reason; every search goes to the audit log, nothing is kept. */
export default function FlowLookup() {
  const { t } = useTranslation()
  const [form, setForm] = useState<FlowQuery>({ seat: '', source: '', destination: '', ports: '', window: '1h', reason: '' })
  const [asked, setAsked] = useState<FlowQuery | null>(null)
  const set = (k: keyof FlowQuery) => (e: { currentTarget: { value: string } }) => setForm({ ...form, [k]: e.currentTarget.value })
  const search = useMutation({ mutationFn: searchFlows, onSuccess: (_a, q) => setAsked(q) })
  const csv = useMutation({ mutationFn: downloadFlows })
  const named = Boolean(form.seat?.trim() || form.source?.trim() || form.destination?.trim() || form.ports?.trim())
  const ready = named && form.reason.trim().length >= REASON_MIN
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (ready) search.mutate(form)
  }
  const answer: FlowLookupAnswer | undefined = search.data

  const columns: DataColumn<FlowRow>[] = [
    { id: 'time', header: t('flowLookup.time'), cell: (r) => dayClock(r.t), mono: true, card: 'inline' },
    { id: 'source', header: t('flowLookup.source'), cell: (r) => side(r.src, r.src_seat), mono: true },
    { id: 'destination', header: t('flowLookup.destination'), cell: (r) => side(r.dst, r.dst_seat), mono: true },
    { id: 'owner', header: t('flowLookup.owner'), cell: (r) => (r.owner ? `${r.owner.name} (AS${r.owner.asn})` : '—'), hideOnPhone: true, wrap: true },
    { id: 'port', header: t('flowLookup.port'), cell: (r) => `${r.protocol}/${r.sport} → ${r.dport}`, mono: true, card: 'label' },
    { id: 'application', header: t('flowLookup.application'), cell: (r) => r.application ?? '—', hideOnPhone: true },
    { id: 'bytes', header: t('flowLookup.bytes'), cell: (r) => bytes(r.bytes), numeric: true, card: 'label' },
    { id: 'packets', header: t('flowLookup.packets'), cell: (r) => r.packets.toLocaleString(), numeric: true, hideOnPhone: true },
  ]
  const failed = answer?.agents.filter((a) => a.error) ?? []

  return (
    <Layout title={t('flowLookup.title')}>
      <PageHead title={t('flowLookup.title')} desc={t('flowLookup.intro')} />
      <Stack gap="md">
        <Paper withBorder p="md" component="form" onSubmit={submit}>
          <Stack gap="sm">
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
              <TextInput label={t('flowLookup.seat')} placeholder="D-5" value={form.seat} onChange={set('seat')} />
              <TextInput label={t('flowLookup.sourceAddress')} placeholder="192.0.2.45" value={form.source} onChange={set('source')} />
              <TextInput label={t('flowLookup.destination')} placeholder={t('flowLookup.destinationHint')}
                value={form.destination} onChange={set('destination')} />
              <TextInput label={t('flowLookup.port')} placeholder="udp/6881-6889" value={form.ports} onChange={set('ports')} />
            </SimpleGrid>
            <Group align="flex-end" gap="sm" wrap="wrap">
              <Select label={t('flowLookup.when')} w={160} allowDeselect={false} value={form.window}
                data={WINDOWS.map((w) => ({ value: w, label: t(`flowLookup.window.${w}`) }))}
                onChange={(v) => v && setForm({ ...form, window: v as FlowWindow })} />
              <TextInput style={{ flex: 1, minWidth: 220 }} label={t('flowLookup.reason')} required
                description={t('flowLookup.reasonHint')} value={form.reason} onChange={set('reason')} maxLength={300} />
              <Button type="submit" disabled={!ready} loading={search.isPending}>{t('flowLookup.search')}</Button>
            </Group>
            {!named && <Text size="xs" c="dimmed">{t('flowLookup.nameSomething')}</Text>}
          </Stack>
        </Paper>
        {search.error && <ErrorBanner error={search.error} />}
        {csv.error && <ErrorBanner error={csv.error} />}
        {answer && (
          <Paper withBorder p="md">
            <Stack gap="sm">
              <Group justify="space-between" wrap="wrap">
                <Text fw={600}>
                  {t('flowLookup.found', { count: answer.total })}
                  <Text span c="dimmed" size="sm"> · {bytes(answer.bytes)}
                    {answer.peers != null ? ` · ${t('flowLookup.peers', { count: answer.peers })}` : ''}
                  </Text>
                </Text>
                {asked && answer.total > 0 && (
                  <Button variant="default" size="xs" loading={csv.isPending} onClick={() => csv.mutate(asked)}>
                    {t('flowLookup.csv')}
                  </Button>
                )}
              </Group>
              {answer.total > answer.rows.length && <Text size="xs" c="dimmed">{t('flowLookup.newest', { count: answer.rows.length })}</Text>}
              {answer.stopped && <Alert color="yellow" variant="light">{t('flowLookup.stopped')}</Alert>}
              {failed.map((a) => (
                <Alert key={a.name} color="yellow" variant="light">{t('flowLookup.agentFailed', { name: a.name, error: a.error })}</Alert>
              ))}
              <DataTable bare cards label={t('flowLookup.title')} rows={answer.rows} columns={columns} minWidth={760}
                rowKey={(r, i) => `${r.agent}-${r.t}-${r.src}-${r.dst}-${r.sport}-${r.dport}-${i}`}
                empty={<EmptyState title={t('flowLookup.none')} />} />
            </Stack>
          </Paper>
        )}
      </Stack>
    </Layout>
  )
}
