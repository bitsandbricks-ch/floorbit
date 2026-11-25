import { Alert, Anchor, Badge, Button, Code, CopyButton, Group, Loader, Modal, Stack, Switch, Text, TextInput, VisuallyHidden } from '@mantine/core'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMoreLines } from '@/components/MoreLines'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { DataTable } from '@bitsandbricks/ui'
import { ago, dateTime } from '@/lib/time'
import { useTelemetryDevices, type DeviceProblem, type TestResult } from './api'

// One device's telemetry at a glance: why it is silent, "Test now" and "Raw data". Used on
// the Telemetry page and meant for a device's own Telemetry view as well; the API is
// /api/telemetry/{devices,test,raw} (floorbit/blueprints/telemetry.py).

const PROBLEM_DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/telemetry.md#when-a-device-sends-nothing'

/** One problem, laid out the same way everywhere: what kind, where (the whole device, one VLAN or
 *  one table), since when, then the hint. The collector's own line opens on demand (issue #1014). */
export function ProblemLine({ p }: { p: DeviceProblem }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const driver = t(`telemetry.driver.${p.driver}`, { defaultValue: p.driver })
  const snmpTimeout = p.kind === 'timeout' && p.driver === 'snmp'
  const key = snmpTimeout ? (p.vlan ? 'timeout_vlan' : p.table ? 'timeout_table' : 'timeout_snmp') : p.kind
  const text = t(`telemetry.problem.${key}`, { driver, address: p.address || '–', detail: p.detail, vlan: p.vlan, table: p.table, defaultValue: p.hint || p.detail })
  // The hint sentences start with "<driver>: "; the line above already names the driver.
  const rest = text.replace(/^[^:]{1,24}: /, '')
  const hint = rest.charAt(0).toUpperCase() + rest.slice(1)
  const scope = p.vlan ? t('telemetry.problem.scopeVlan', { vlan: p.vlan })
    : p.table ? t('telemetry.problem.scopeTable', { table: p.table }) : t('telemetry.problem.scopeDevice')
  const color = p.kind === 'other' ? 'warn' : 'down'
  return (
    <Stack gap={2} mt={6} pl="xs" style={{ borderLeft: `2px solid var(--mantine-color-${color}-filled)` }}>
      <Group gap={6} wrap="wrap">
        <Badge size="xs" color={color} variant="light" tt="none">{t(`telemetry.problemKind.${p.kind}`, { defaultValue: p.kind })}</Badge>
        <Text size="xs" fw={600}>{driver} · {scope}</Text>
        {p.since ? <Text size="xs" c="dimmed" title={dateTime(p.since)}>{t('telemetry.problem.since', { ago: ago(p.since) })}</Text> : null}
        {(p.count ?? 0) > 1 && <Text size="xs" c="dimmed">{t('telemetry.problem.count', { count: p.count })}</Text>}
      </Group>
      <Text size="xs" style={{ overflowWrap: 'anywhere' }}>{hint}</Text>
      <Group gap="sm">
        <Anchor component="button" type="button" size="xs" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? t('telemetry.problem.hideLine') : t('telemetry.problem.showLine')}
        </Anchor>
        <Anchor href={PROBLEM_DOCS} target="_blank" rel="noreferrer" size="xs">{t('telemetry.problem.docs')}</Anchor>
      </Group>
      {open && (
        <Code block style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11 }}>
          {[p.address && `${p.address}`, p.detail, p.at && t('telemetry.problem.lastAt', { at: dateTime(p.at) })].filter(Boolean).join('\n')}
        </Code>
      )}
    </Stack>
  )
}

export function DeviceProblems({ problems }: { problems?: DeviceProblem[] }) {
  if (!problems?.length) return null
  return <>{problems.map((p) => <ProblemLine key={`${p.driver}-${p.kind}-${p.vlan ?? ''}`} p={p} />)}</>
}

/** The first lines, then "Show all": no scroll box inside the dialog (#935). */
function RawLines({ lines, first = 40 }: { lines: string[]; first?: number }) {
  const { t } = useTranslation()
  const { limit, more } = useMoreLines(lines.length, first)
  if (!lines.length) return <Text size="sm" c="dimmed">{t('telemetry.raw.none')}</Text>
  return (
    <Stack gap={4} align="flex-start">
      <Code block w="100%" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11 }}>{lines.slice(0, limit).join('\n')}</Code>
      {more}
    </Stack>
  )
}

function TestView({ r }: { r: TestResult }) {
  const { t } = useTranslation()
  const [raw, setRaw] = useState(false)
  return (
    <Stack gap="sm">
      <Group gap="xs">
        <Badge color={r.ok ? 'up' : r.points ? 'warn' : 'down'} variant="light" tt="none">
          {r.ok ? t('telemetry.test.ok') : r.points ? t('telemetry.test.partly') : t('telemetry.test.nothing')}
        </Badge>
        <Text size="sm" c="dimmed">{t('telemetry.test.took', { agent: r.agent, ms: r.took_ms })}</Text>
      </Group>
      {r.points > 0 && (
        <Text size="sm">
          {t('telemetry.test.got', { count: r.points, ports: r.summary.ports })}
          {r.summary.sys_name && <> · <Text span ff="monospace" size="sm">{r.summary.sys_name}</Text></>}
        </Text>
      )}
      {Object.keys(r.summary.measurements).length > 0 && (
        <Group gap={4}>{Object.entries(r.summary.measurements).map(([m, n]) => <Badge key={m} variant="default" tt="none" size="sm">{m} {n}</Badge>)}</Group>
      )}
      <DeviceProblems problems={r.problems} />
      {r.notes.map((n) => <Text key={n} size="xs" c="dimmed" ff="monospace" style={{ overflowWrap: 'anywhere' }}>{n}</Text>)}
      {r.raw.length > 0 && (
        <>
          <Button variant="subtle" size="compact-sm" onClick={() => setRaw((v) => !v)} style={{ alignSelf: 'flex-start' }}>
            {raw ? t('telemetry.raw.hide') : t('telemetry.raw.show', { count: r.raw.length })}
          </Button>
          {raw && <RawLines lines={r.raw} />}
        </>
      )}
    </Stack>
  )
}

/** The measurement of one line protocol line: what comes before the first unescaped comma or space. */
function measurement(line: string): string {
  const m = /^((?:\\.|[^,\s\\])+)/.exec(line)
  return m ? m[1] : ''
}

/** One device's raw lines on a tab of its own: refreshing, filtered by measurement or text, with
 *  a pause to read and a copy for a bug report. Same API as the dialog (/api/telemetry/raw). */
export function DeviceRawData({ name }: { name: string }) {
  const { t } = useTranslation()
  const [paused, setPaused] = useState(false)
  const [text, setText] = useState('')
  const [only, setOnly] = useState<string | null>(null)
  const raw = useQuery({
    queryKey: qk.telemetryRaw(name), refetchInterval: paused ? false : 10_000,
    queryFn: () => get<{ lines: string[]; agent: string }>(`/api/telemetry/raw?name=${encodeURIComponent(name)}`),
  })
  if (raw.isLoading) return <Loader size="sm" />
  if (raw.error) return <Alert color="down">{raw.error.message}</Alert>
  const lines = raw.data?.lines ?? []
  const counts = new Map<string, number>()
  for (const l of lines) counts.set(measurement(l), (counts.get(measurement(l)) ?? 0) + 1)
  const needle = text.trim().toLowerCase()
  const shown = lines.filter((l) => (!only || measurement(l) === only) && (!needle || l.toLowerCase().includes(needle)))
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">{paused ? t('telemetry.raw.pausedHelp', { agent: raw.data?.agent ?? '' }) : t('telemetry.raw.help', { agent: raw.data?.agent ?? '' })}</Text>
      <Group gap="sm" wrap="wrap">
        <TextInput size="xs" placeholder={t('telemetry.raw.filter')} aria-label={t('telemetry.raw.filter')}
          value={text} onChange={(e) => setText(e.currentTarget.value)} style={{ flex: '1 1 220px', maxWidth: 360 }} />
        <Switch size="sm" label={t('telemetry.raw.pause')} checked={paused} onChange={(e) => setPaused(e.currentTarget.checked)} />
        <CopyButton value={shown.join('\n')}>
          {({ copied, copy }) => (
            <Button size="compact-sm" variant="default" onClick={copy} disabled={!shown.length}>
              {copied ? t('telemetry.raw.copied') : t('telemetry.raw.copy')}
            </Button>
          )}
        </CopyButton>
        <Text size="xs" c="dimmed">{t('telemetry.raw.shown', { shown: shown.length, count: lines.length })}</Text>
      </Group>
      {counts.size > 1 && (
        <Group gap={4} role="group" aria-label={t('telemetry.raw.measurements')}>
          {[...counts.entries()].sort((a, b) => b[1] - a[1]).map(([m, n]) => (
            <Badge key={m} component="button" type="button" tt="none" size="sm" style={{ cursor: 'pointer' }}
              variant={only === m ? 'filled' : 'default'} aria-pressed={only === m}
              onClick={() => setOnly(only === m ? null : m)}>{m} {n}</Badge>
          ))}
        </Group>
      )}
      {lines.length && !shown.length ? <Text size="sm" c="dimmed">{t('telemetry.raw.noMatch')}</Text>
        : <RawLines key={only ?? ''} lines={shown} first={80} />}
    </Stack>
  )
}

/** "Test now" and "Raw data" for one device, with their dialogs. ``raw={false}`` where the page
 *  has a Raw data tab of its own. */
export function DeviceTelemetryActions({ name, setup = false, raw: rawButton = true }: { name: string; setup?: boolean; raw?: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<'test' | 'raw' | 'setup' | null>(null)
  const test = useMutation({ mutationFn: () => post<TestResult>('/api/telemetry/test', { name }) })
  const raw = useQuery({
    queryKey: qk.telemetryRaw(name), enabled: open === 'raw', refetchInterval: open === 'raw' ? 10_000 : false,
    queryFn: () => get<{ lines: string[]; agent: string }>(`/api/telemetry/raw?name=${encodeURIComponent(name)}`),
  })
  // What to paste on the device so it sends (traps, MDT, its own Telegraf).
  const config = useQuery({
    queryKey: qk.telemetryDeviceConfig(name), enabled: open === 'setup',
    queryFn: () => get<{ config: string }>(`/api/telemetry/device-config?name=${encodeURIComponent(name)}`),
  })
  const titles = { test: 'telemetry.test.title', raw: 'telemetry.raw.title', setup: 'telemetry.pasteTitle' } as const
  return (
    <>
      <Button size="compact-sm" variant="default" loading={test.isPending}
        onClick={() => { setOpen('test'); test.mutate() }}>{t('telemetry.test.button')}</Button>
      {rawButton && <Button size="compact-sm" variant="default" onClick={() => setOpen('raw')}>{t('telemetry.raw.button')}</Button>}
      {setup && <Button size="compact-sm" variant="default" onClick={() => setOpen('setup')}>{t('telemetry.deviceConfig')}</Button>}
      <Modal opened={open !== null} onClose={() => setOpen(null)} size="xl" title={open ? t(titles[open], { name }) : ''}>
        {open === 'test' && (test.isPending ? <Group gap="xs"><Loader size="sm" /><Text size="sm">{t('telemetry.test.running')}</Text></Group>
          : test.error ? <Alert color="down">{test.error.message}</Alert>
            : test.data ? <TestView r={test.data} /> : null)}
        {open === 'raw' && (raw.isLoading ? <Loader size="sm" />
          : raw.error ? <Alert color="down">{raw.error.message}</Alert>
            : raw.data ? <Stack gap="xs"><Text size="xs" c="dimmed">{t('telemetry.raw.help', { agent: raw.data.agent })}</Text><RawLines lines={raw.data.lines} /></Stack> : null)}
        {open === 'setup' && (config.isLoading ? <Loader size="sm" />
          : config.error ? <Alert color="down">{config.error.message}</Alert>
            : <Stack gap="sm"><Text size="sm">{t('telemetry.pasteIntro')}</Text>
              {config.data?.config ? <Code block>{config.data.config}</Code> : <Text c="dimmed">{t('telemetry.pasteNothing')}</Text>}</Stack>)}
      </Modal>
    </>
  )
}

/** Last heard and the problems of one device, fetching its own data. */
export function DeviceTelemetryStatus({ name }: { name: string }) {
  const { t } = useTranslation()
  const devices = useTelemetryDevices()
  const s = devices.data?.devices[name]
  return (
    <Stack gap={4}>
      {s?.seen ? <Badge color={s.online ? 'up' : 'down'} variant="light" tt="none" w="fit-content" title={dateTime(s.seen)}>{t('telemetry.heard', { when: ago(s.seen) })}</Badge>
        : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>}
      <DeviceProblems problems={s?.problems} />
    </Stack>
  )
}

/** Every device telemetry collects from: last heard, problems, Test now and Raw data. */
export function TelemetryDevicesTable() {
  const { t } = useTranslation()
  const devices = useTelemetryDevices()
  const rows = Object.entries(devices.data?.devices ?? {})
  if (devices.error) return <Alert color="down">{devices.error.message}</Alert>
  if (!rows.length) return <Text size="sm" c="dimmed">{t('telemetry.empty')}</Text>
  return (
    <DataTable rows={rows} rowKey={([name]) => name} label={t('telemetry.tableLabel')} urlState={false} pageSize={0} minWidth={420}
      defaultSort={{ id: 'device' }}
      columns={[
        { id: 'device', header: t('telemetry.device'), sort: ([name]) => name,
          cell: ([name, s]) => <><Text ff="monospace" size="sm">{name}</Text><DeviceProblems problems={s.problems} /></> },
        { id: 'seen', header: t('telemetry.lastSeen'), descFirst: true, sort: ([, s]) => s.seen ?? 0,
          cell: ([, s]) => (s.seen ? <Badge color={s.online ? 'up' : 'down'} variant="light" tt="none" title={dateTime(s.seen)}>{ago(s.seen)}</Badge>
            : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>) },
        { id: 'actions', header: <VisuallyHidden>{t('telemetry.open')}</VisuallyHidden>,
          cell: ([name]) => <Group gap={6} justify="flex-end" wrap="nowrap"><DeviceTelemetryActions name={name} /></Group> },
      ]} />
  )
}
