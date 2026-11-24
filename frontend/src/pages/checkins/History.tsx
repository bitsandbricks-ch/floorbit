import { Alert, Anchor, Badge, Button, Group, Paper, SegmentedControl, Select, SimpleGrid, Text, TextInput } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable } from '@bitsandbricks/ui'
import { DateTimeInput } from '@/components/DateTimeInput'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { EntitySelect } from '@/components/EntitySelect'

type View = 'sessions' | 'events'
const EVENTS = ['checkin', 'moved', 'removed', 'ip_changed', 'mac_found'] as const

interface SessionRow {
  seat: string; username: string; mac: string; ips: string[]
  start: number; end: number | null; start_local: string; end_local: string; end_reason?: string
}
interface EventRow {
  ts: number; time_local: string; event: string; seat: string; username: string; ip: string; mac: string
  to_seat?: string; previous_ip?: string
}
interface HistoryAnswer { view: View; total: number; enabled: boolean; rows: (SessionRow | EventRow)[] }

type Filters = Record<'seat' | 'user' | 'ip' | 'mac' | 'since' | 'until' | 'event', string>
const EMPTY: Filters = { seat: '', user: '', ip: '', mac: '', since: '', until: '', event: '' }

function duration(start: number, end: number | null) {
  const mins = Math.round(((end ?? Date.now() / 1000) - start) / 60)
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  return h < 24 ? `${h} h ${mins % 60} min` : `${Math.floor(h / 24)} d ${h % 24} h`
}

/** Who sat where, and every check-in event, for the crew (what /checkins/history showed as its own page). */
export function History() {
  const { t } = useTranslation()
  const [view, setView] = useState<View>('sessions')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const params = new URLSearchParams({ view })
  for (const [k, v] of Object.entries(filters)) if (v && (k !== 'event' || view === 'events')) params.set(k, v)
  const query = params.toString()
  const data = useQuery({
    queryKey: qk.checkinHistory(query),
    queryFn: () => get<HistoryAnswer>(`/api/checkins/history?${query}`),
    placeholderData: keepPreviousData,
  })
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  // Clicking a seat, a user, an IP or a MAC filters on it.
  const pick = (field: keyof Filters, value: string | undefined) =>
    value ? <Anchor component="button" type="button" size="sm" ff={field === 'ip' || field === 'mac' ? 'monospace' : undefined}
      onClick={() => set({ [field]: value })}>{value}</Anchor> : <Text span c="dimmed">–</Text>
  const label = (e: string | undefined) => (e ? t(`crewCheckin.history.event.${e}`, { defaultValue: e }) : '')

  const d = data.data
  const rows = d?.rows ?? []
  return (
    <>
      <Group justify="space-between" mb="sm" wrap="wrap">
        <SegmentedControl value={view} onChange={(v) => setView(v as View)}
          data={[{ value: 'sessions', label: t('crewCheckin.history.sessions') }, { value: 'events', label: t('crewCheckin.history.events') }]} />
        <Button component="a" href={`/api/checkins/history.csv?${query}`} variant="default" leftSection={<IconDownload size={16} />}>
          {t('crewCheckin.history.export')}
        </Button>
      </Group>
      <Paper withBorder radius="lg" p="sm" mb="sm">
        <SimpleGrid cols={{ base: 1, xs: 2, md: view === 'events' ? 7 : 6 }} spacing="sm">
          <EntitySelect kind="seats" label={t('crewCheckin.history.seat')} value={filters.seat} onChange={(v) => set({ seat: v })} />
          <TextInput label={t('crewCheckin.history.user')} placeholder={t('crewCheckin.history.contains')} value={filters.user}
            onChange={(e) => set({ user: e.currentTarget.value })} />
          <TextInput label="IP" placeholder="192.0.2." ff="monospace" value={filters.ip} onChange={(e) => set({ ip: e.currentTarget.value })} />
          <TextInput label="MAC" placeholder="02:00:00" value={filters.mac} onChange={(e) => set({ mac: e.currentTarget.value })} />
          <DateTimeInput label={t('crewCheckin.history.from')} value={filters.since} onChange={(v) => set({ since: v })} />
          <DateTimeInput label={t('crewCheckin.history.to')} value={filters.until} onChange={(v) => set({ until: v })} />
          {view === 'events' && (
            <Select label={t('crewCheckin.history.event.label')} placeholder={t('crewCheckin.history.any')} clearable value={filters.event || null}
              data={EVENTS.map((e) => ({ value: e, label: label(e) }))} onChange={(v) => set({ event: v ?? '' })} />
          )}
        </SimpleGrid>
        {Object.values(filters).some(Boolean) && (
          <Button variant="subtle" size="compact-sm" mt="xs" onClick={() => setFilters(EMPTY)}>{t('crewCheckin.history.clear')}</Button>
        )}
      </Paper>
      {data.error && <Alert color="down" role="alert" mb="sm">{data.error.message}</Alert>}
      {d && !d.enabled && <Alert color="warn" mb="sm">{t('crewCheckin.history.off')}</Alert>}
      {d && (
        <Text size="sm" c="dimmed" mb="xs">
          {d.total === rows.length ? t(`crewCheckin.history.count.${view}`, { count: d.total })
            : t('crewCheckin.history.showing', { shown: rows.length, total: d.total })}
        </Text>
      )}
      {d && (view === 'sessions' ? (
        <DataTable key="sessions" label={t('crewCheckin.history.sessions')} rows={rows as SessionRow[]} rowKey={(r) => `${r.seat}-${r.start}`}
          defaultSort={{ id: 'in', desc: true }} minWidth={820} empty={<Text>{t('crewCheckin.history.none')}</Text>}
          columns={[
            { id: 'seat', header: t('crewCheckin.history.col.seat'), sort: (r) => r.seat ?? '', cell: (r) => pick('seat', r.seat) },
            { id: 'user', header: t('crewCheckin.history.col.user'), sort: (r) => r.username ?? '', cell: (r) => pick('user', r.username) },
            { id: 'mac', header: t('crewCheckin.history.col.mac'), sort: (r) => r.mac ?? '', hideOnPhone: true, cell: (r) => pick('mac', r.mac) },
            { id: 'ips', header: t('crewCheckin.history.col.ips'), hideOnPhone: true, cell: (r) =>
              (r.ips.length ? r.ips.map((ip, i) => <span key={ip}>{i > 0 && ', '}{pick('ip', ip)}</span>) : '–') },
            { id: 'in', header: t('crewCheckin.history.col.in'), sort: (r) => r.start, cell: (r) => r.start_local },
            { id: 'left', header: t('crewCheckin.history.col.left'), sort: (r) => r.end ?? Number.MAX_SAFE_INTEGER, cell: (r) => (r.end
              ? <>{r.end_local} {r.end_reason && <Badge size="sm" variant="light" tt="none">{label(r.end_reason)}</Badge>}</>
              : <Badge size="sm" variant="light" color="up" tt="none">{t('crewCheckin.history.here')}</Badge>) },
            { id: 'duration', header: t('crewCheckin.history.col.duration'), numeric: true,
              sort: (r) => (r.end ?? Date.now() / 1000) - r.start, cell: (r) => duration(r.start, r.end) },
          ]} />
      ) : (
        <DataTable key="events" label={t('crewCheckin.history.events')} rows={rows as EventRow[]} rowKey={(r, n) => `${r.ts}-${n}`}
          defaultSort={{ id: 'time', desc: true }} minWidth={820} empty={<Text>{t('crewCheckin.history.none')}</Text>}
          columns={[
            { id: 'time', header: t('crewCheckin.history.col.time'), sort: (r) => r.ts, cell: (r) => r.time_local },
            { id: 'event', header: t('crewCheckin.history.col.event'), sort: (r) => label(r.event),
              cell: (r) => <Badge size="sm" variant="light" tt="none">{label(r.event)}</Badge> },
            { id: 'seat', header: t('crewCheckin.history.col.seat'), sort: (r) => r.seat ?? '', cell: (r) => pick('seat', r.seat) },
            { id: 'user', header: t('crewCheckin.history.col.user'), sort: (r) => r.username ?? '', cell: (r) => pick('user', r.username) },
            { id: 'ip', header: t('crewCheckin.history.col.ip'), sort: (r) => r.ip ?? '', cell: (r) => pick('ip', r.ip) },
            { id: 'mac', header: t('crewCheckin.history.col.mac'), sort: (r) => r.mac ?? '', hideOnPhone: true, cell: (r) => pick('mac', r.mac) },
            { id: 'details', header: t('crewCheckin.history.col.details'), hideOnPhone: true, cell: (r) => (
              <Text span size="sm" c="dimmed">
                {r.to_seat ? t('crewCheckin.history.toSeat', { seat: r.to_seat }) : r.previous_ip ? t('crewCheckin.history.wasIp', { ip: r.previous_ip }) : ''}
              </Text>
            ) },
          ]} />
      ))}
    </>
  )
}
