import { Alert, Anchor, Badge, Button, ColorInput, FileButton, Group, Image, NumberInput, Paper, PasswordInput, Select, SimpleGrid, Stack, Switch, Text, TextInput, ThemeIcon } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconCircleCheck, IconCircleX, IconDownload, IconUpload } from '@tabler/icons-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { contrast } from '@/colorContrast'
import { useFeature } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'

type FieldType = 'url' | 'text' | 'secret' | 'list' | 'bool' | 'int' | 'choice' | 'color' | 'image'
type Field = {
  key: string; section: string; label: string; type: FieldType; env: string | null
  help?: string; placeholder?: string; unit?: string; min?: number; max?: number; theme?: string
  options?: { value: string; label: string }[]
}
type Value = { source: 'saved' | 'env' | 'default'; value?: unknown; is_set?: boolean; env?: string; env_set?: boolean }
export type SettingsAnswer = {
  sections: { id: string; title: string; description: string }[]
  fields: Field[]
  values: Record<string, Value>
  status: { netbox_enabled: boolean; librenms_enabled: boolean; redis: { connected: boolean; host?: string; port?: number } | null }
}
type TestResult = { ok: boolean; message: string }
type Changes = Record<string, unknown>   // key -> new value, or null for "reset"

const TESTABLE = new Set(['netbox', 'librenms'])
const HEX = /^#[0-9a-f]{6}$/i
// i18next splits keys on dots; the setting keys have them.
const k = (key: string) => key.replace(/\./g, '_')

/** Is a typed value one the server takes? Bad ones stay unsaved and mark the field. */
function invalid(f: Field, v: unknown): boolean {
  if (f.type === 'url') return typeof v === 'string' && v !== '' && !/^https?:\/\//i.test(v)
  if (f.type === 'color') return typeof v === 'string' && v !== '' && !HEX.test(v)
  if (f.type === 'int') return typeof v !== 'number' || !Number.isInteger(v) || (f.min != null && v < f.min) || (f.max != null && v > f.max)
  return false
}

function TestLine({ result }: { result: TestResult | 'running' | null }) {
  const { t } = useTranslation()
  if (!result) return null
  if (result === 'running') return <Text size="sm" c="dimmed" role="status">{t('settings.testing')}</Text>
  return (
    <Group gap={6} wrap="nowrap" role="status">
      <ThemeIcon size="sm" variant="transparent" color={result.ok ? 'up' : 'down'}>
        {result.ok ? <IconCircleCheck size={16} /> : <IconCircleX size={16} />}
      </ThemeIcon>
      <Text size="sm" c={result.ok ? 'up' : 'down'}>{result.message}</Text>
    </Group>
  )
}

/** Runs a connection test with the form's unsaved values for that service. */
function useTest(changes: Changes) {
  const [results, setResults] = useState<Record<string, TestResult | 'running'>>({})
  const run = async (service: string) => {
    setResults((r) => ({ ...r, [service]: 'running' }))
    const body: Changes = {}
    for (const [key, v] of Object.entries(changes)) if (key.startsWith(service + '.') && v !== null) body[key] = v
    try {
      const r = await post<TestResult>(`/api/settings/test/${service}`, body)
      setResults((rs) => ({ ...rs, [service]: r }))
    } catch (e) {
      setResults((rs) => ({ ...rs, [service]: { ok: false, message: (e as Error).message } }))
    }
  }
  return { results, run }
}

function Connections({ status, test }: { status: SettingsAnswer['status']; test: ReturnType<typeof useTest> }) {
  const { t } = useTranslation()
  const redis = status.redis ?? { connected: false }
  const where = `${redis.host ?? '?'}:${redis.port ?? '?'}`
  const items: [string, boolean, string][] = [
    ['NetBox', status.netbox_enabled, t(status.netbox_enabled ? 'settings.configured' : 'settings.netboxOff')],
    ['LibreNMS', status.librenms_enabled, t(status.librenms_enabled ? 'settings.configured' : 'settings.librenmsOff')],
    ['Redis', redis.connected, redis.connected ? where : t('settings.redisOff', { where })],
  ]
  return (
    <Panel title={t('settings.connections')}>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        {items.map(([name, on, sub]) => (
          <Paper key={name} withBorder radius="md" p="sm">
            <Group gap="xs" wrap="nowrap">
              <ThemeIcon size={10} radius="xl" color={on ? 'up' : 'down'} aria-hidden><span /></ThemeIcon>
              <Text fw={600} size="sm">{name}</Text>
            </Group>
            <Text size="xs" c="dimmed" mt={2} style={{ overflowWrap: 'anywhere' }}>{sub}</Text>
          </Paper>
        ))}
      </SimpleGrid>
      <Group mt="md" gap="sm">
        <Button variant="default" size="xs" onClick={() => void test.run('redis')}>{t('settings.testRedis')}</Button>
        <TestLine result={test.results.redis ?? null} />
      </Group>
      <Text size="xs" c="dimmed" mt="xs">{t('settings.redisHelp')}</Text>
    </Panel>
  )
}

type Backup = { format?: string; created?: string; layout?: { switches?: unknown[]; positions?: object; seat_blocks?: unknown[] }; settings?: object }

function BackupPanel() {
  const { t } = useTranslation()
  const [pending, setPending] = useState<{ name: string; backup: Backup } | null>(null)
  const [result, setResult] = useState<TestResult | null>(null)
  const restore = useMutation({
    mutationFn: (b: Backup) => post<{ skipped_settings?: string[] }>('/api/settings/backup', b),
    onSuccess: (r) => {
      setPending(null)
      const skipped = r.skipped_settings?.length ? ' ' + t('settings.backup.skipped', { count: r.skipped_settings.length }) : ''
      setResult({ ok: true, message: t('settings.backup.restored') + skipped })
      // Settings and the theme come from the server with the page, so load it again.
      setTimeout(() => window.location.reload(), 1200)
    },
    onError: (e) => setResult({ ok: false, message: (e as Error).message }),
  })
  const pick = async (file: File | null) => {
    if (!file) return
    setResult(null)
    let backup: Backup
    try { backup = JSON.parse(await file.text()) as Backup } catch {
      setPending(null); setResult({ ok: false, message: t('settings.backup.notJson') }); return
    }
    if (!backup || backup.format !== 'floorbit-backup') {
      setPending(null); setResult({ ok: false, message: t('settings.backup.notBackup') }); return
    }
    setPending({ name: file.name, backup })
  }
  const summary = (() => {
    if (!pending) return ''
    const l = pending.backup.layout ?? {}
    const created = pending.backup.created ? new Date(pending.backup.created) : null
    return t('settings.backup.summary', {
      name: pending.name,
      made: created && !Number.isNaN(created.getTime()) ? t('settings.backup.made', { when: created.toLocaleString() }) : '',
      switches: t('settings.backup.switches', { count: (l.switches?.length ?? 0) + Object.keys(l.positions ?? {}).length }),
      blocks: t('settings.backup.blocks', { count: l.seat_blocks?.length ?? 0 }),
      settings: t('settings.backup.settings', { count: Object.keys(pending.backup.settings ?? {}).length }),
    })
  })()
  return (
    <Panel title={t('settings.backup.title')} desc={t('settings.backup.desc')}>
      <Group gap="sm">
        <Button component="a" href="/api/settings/backup" download variant="default" leftSection={<IconDownload size={16} />}>
          {t('settings.backup.download')}
        </Button>
        <FileButton onChange={(f) => void pick(f)} accept=".json,application/json">
          {(props) => <Button {...props} variant="default" leftSection={<IconUpload size={16} />}>{t('settings.backup.restore')}</Button>}
        </FileButton>
      </Group>
      {pending && (
        <Alert mt="md" color="warn" variant="light" role="alertdialog" aria-label={t('settings.backup.restore')}>
          <Text size="sm" mb="sm">{summary}</Text>
          <Group gap="sm">
            <Button color="down" loading={restore.isPending} onClick={() => restore.mutate(pending.backup)}>{t('settings.backup.go')}</Button>
            <Button variant="default" onClick={() => setPending(null)}>{t('common.cancel')}</Button>
          </Group>
        </Alert>
      )}
      {result && <Stack mt="sm"><TestLine result={result} /></Stack>}
    </Panel>
  )
}

function FieldRow({ field, info, change, onChange, onReset, onUndo }: {
  field: Field; info: Value; change: unknown; onChange: (v: unknown) => void; onReset: () => void; onUndo: () => void
}) {
  const { t } = useTranslation()
  const dirty = change !== undefined
  const resetting = change === null
  const value = dirty && !resetting ? change : info.value
  const label = t(`settings.fields.${k(field.key)}.label`, { defaultValue: field.label })
  const help = field.help ? t(`settings.fields.${k(field.key)}.help`, { defaultValue: field.help }) : undefined
  const placeholder = field.placeholder ? t(`settings.fields.${k(field.key)}.placeholder`, { defaultValue: field.placeholder }) : undefined
  const error = dirty && !resetting && invalid(field, change) ? t('settings.invalid') : undefined
  const common = { label, description: help, disabled: resetting, error }
  const wide = { maw: 560 }   // long enough for a URL, short enough to read

  let input: ReactNode
  switch (field.type) {
    case 'bool':
      input = <Switch {...common} error={undefined} checked={!!value} onChange={(e) => onChange(e.currentTarget.checked)} />
      break
    case 'secret':
      input = <PasswordInput {...common} {...wide} autoComplete="new-password" value={typeof change === 'string' ? change : ''}
        placeholder={info.is_set ? t('settings.secretSet') : t('settings.secretUnset')} onChange={(e) => onChange(e.currentTarget.value)} />
      break
    case 'int':
      input = <NumberInput {...common} maw={260} value={value as number} min={field.min} max={field.max} allowDecimal={false}
        rightSection={field.unit ? <Text size="xs" c="dimmed" pr="xs">{t(`settings.unit.${field.unit}`, { defaultValue: field.unit })}</Text> : undefined}
        rightSectionWidth={field.unit ? 70 : undefined}
        onChange={(v) => onChange(v === '' ? '' : Number(v))} />
      break
    case 'choice':
      input = <Select {...common} maw={360} allowDeselect={false} value={value as string}
        data={(field.options ?? []).map((o) => ({ value: o.value, label: t(`settings.presets.${o.value}`, { defaultValue: o.label }) }))}
        onChange={(v) => v && onChange(v)} />
      break
    case 'color':
      input = <ColorInput {...common} maw={260} format="hex" value={(value as string) || ''} placeholder={t('settings.derived')}
        onChange={(v) => onChange(v.toLowerCase())} />
      break
    case 'list':
      input = <TextInput {...common} {...wide} value={((value as string[]) ?? []).join(', ')} placeholder={placeholder}
        onChange={(e) => onChange(e.currentTarget.value.split(',').map((s) => s.trim()).filter(Boolean))} />
      break
    case 'image':
      input = <ImageField common={common} value={(value as string) || ''} onChange={onChange} />
      break
    default:
      input = <TextInput {...common} {...wide} type={field.type === 'url' ? 'url' : 'text'} spellCheck={false} placeholder={placeholder}
        value={(value as string) ?? ''} onChange={(e) => onChange(e.currentTarget.value.trim().replace(/\/+$/, ''))} />
  }

  return (
    <Stack gap={4} data-key={field.key}>
      {input}
      <Group gap="xs">
        {dirty
          ? <Badge size="sm" variant="light" color="warn" tt="none">{t(resetting ? 'settings.willReset' : 'settings.unsaved')}</Badge>
          : <Badge size="sm" variant="light" color={info.source === 'saved' ? 'bit' : 'gray'} tt="none">{t(`settings.source.${info.source}`)}</Badge>}
        {field.env && <Text size="xs" c="dimmed" ff="monospace">{field.env}{info.env_set ? ` ${t('settings.envSet')}` : ''}</Text>}
        {info.source === 'saved' && !dirty && (
          <Anchor component="button" type="button" size="xs" onClick={onReset}>
            {t(field.type === 'secret' ? 'settings.removeSecret' : 'settings.reset')}
          </Anchor>
        )}
        {dirty && <Anchor component="button" type="button" size="xs" onClick={onUndo}>{t('settings.undo')}</Anchor>}
      </Group>
    </Stack>
  )
}

function ImageField({ common, value, onChange }: { common: { label: string; description?: string; disabled: boolean }; value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation()
  const [tooBig, setTooBig] = useState(false)
  const pick = (file: File | null) => {
    if (!file) return
    setTooBig(file.size > 256 * 1024)
    if (file.size > 256 * 1024) return
    const reader = new FileReader()
    reader.onload = () => onChange(String(reader.result))
    reader.readAsDataURL(file)
  }
  return (
    <Stack gap={4}>
      <Text size="sm" fw={500}>{common.label}</Text>
      {common.description && <Text size="xs" c="dimmed">{common.description}</Text>}
      <Group gap="sm">
        {value && <Paper withBorder p={4} radius="md"><Image src={value} alt="" h={40} w="auto" fit="contain" /></Paper>}
        <FileButton onChange={pick} accept="image/svg+xml,image/png,image/jpeg,image/webp" disabled={common.disabled}>
          {(props) => <Button {...props} variant="default" size="xs">{t('settings.chooseImage')}</Button>}
        </FileButton>
        {value && <Button variant="subtle" size="xs" color="down" disabled={common.disabled} onClick={() => onChange('')}>{t('settings.removeImage')}</Button>}
      </Group>
      {tooBig && <Text size="xs" c="down" role="alert">{t('settings.imageTooBig', { name: common.label })}</Text>}
    </Stack>
  )
}

function ThemeHint({ current }: { current: (key: string) => unknown }) {
  const { t } = useTranslation()
  if (current('theme.preset') !== 'custom') return <Text size="sm" c="dimmed">{t('settings.themeHint')}</Text>
  const accent = current('theme.accent') as string
  const bg = (current('theme.background') as string) || '#0b0b0f'
  if (!HEX.test(accent ?? '') || !HEX.test(bg)) return null
  const ratio = contrast(accent, bg)
  const ok = ratio >= 3
  return <TestLine result={{ ok, message: t(ok ? 'settings.contrastOk' : 'settings.contrastLow', { ratio: ratio.toFixed(1) }) }} />
}

/** Settings: the schema from GET /api/settings, saving only what changed. ``null`` resets a field
 *  to its environment variable or built-in default. */
export default function Settings() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const wall = useFeature('stats_wall')
  const query = useQuery({ queryKey: qk.settings, queryFn: () => get<SettingsAnswer>('/api/settings') })
  const [changes, setChanges] = useState<Changes>({})
  const [saved, setSaved] = useState<string | null>(null)
  const test = useTest(changes)
  const save = useMutation({
    mutationFn: (body: Changes) => put<SettingsAnswer>('/api/settings', body),
    onSuccess: (answer, body) => {
      qc.setQueryData(qk.settings, answer)
      setChanges({})
      const theme = Object.keys(body).some((key) => key.startsWith('theme.'))
      setSaved(t(theme ? 'settings.savedTheme' : 'settings.saved'))
      // The server puts the theme on <html> with the page, so show a new one by loading it again.
      if (theme) setTimeout(() => window.location.reload(), 600)
    },
  })
  const count = Object.keys(changes).length
  const d = query.data
  const bad = !!d && Object.entries(changes).some(([key, v]) => {
    const f = d.fields.find((x) => x.key === key)
    return !!f && v !== null && invalid(f, v)
  })

  useEffect(() => {
    if (!count) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [count])

  const setField = (f: Field, v: unknown) => {
    setSaved(null)
    const original = f.type === 'secret' ? '' : d?.values[f.key]?.value
    setChanges((c) => {
      const next = { ...c }
      if (JSON.stringify(v) === JSON.stringify(original)) delete next[f.key]
      else next[f.key] = v
      return next
    })
  }
  const drop = (key: string) => setChanges((c) => { const next = { ...c }; delete next[key]; return next })
  const current = (key: string) => (key in changes && changes[key] !== null ? changes[key] : d?.values[key]?.value)

  return (
    <Layout title={t('settings.title')}>
      <PageHead title={t('settings.title')} desc={t('settings.intro')} />
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} mb="md" />
      {query.isPending && <LoadingState rows={4} />}
      {d && (
        <form onSubmit={(e) => { e.preventDefault(); if (count && !bad) save.mutate(changes) }} autoComplete="off" noValidate>
          <Stack gap="md" pb={count ? 96 : 0}>
            {wall && <Text size="sm" c="dimmed">{t('settings.wall')} <Anchor href="/wall">/wall</Anchor></Text>}
            <Connections status={d.status} test={test} />
            <BackupPanel />
            {d.sections.map((s) => {
              const fields = d.fields.filter((f) => f.section === s.id)
              const custom = current('theme.preset') === 'custom'
              return (
                <Panel key={s.id} id={`sec-${s.id}`} title={t(`settings.sections.${s.id}.title`, { defaultValue: s.title })}
                  desc={t(`settings.sections.${s.id}.desc`, { defaultValue: s.description })}
                  actions={TESTABLE.has(s.id) && (
                    <Button variant="default" size="xs" onClick={() => void test.run(s.id)}>{t('settings.test')}</Button>
                  )}>
                  <Stack gap="lg">
                    {TESTABLE.has(s.id) && <TestLine result={test.results[s.id] ?? null} />}
                    {fields.map((f, i) => (
                      <Stack key={f.key} gap="lg" style={f.theme === 'custom' && !custom ? { opacity: 0.55 } : undefined}>
                        {/* Above the Custom-only colours, which its text ("the colours below") points at. */}
                        {s.id === 'appearance' && f.theme === 'custom' && fields[i - 1]?.theme !== 'custom' && <ThemeHint current={current} />}
                        <FieldRow field={f} info={d.values[f.key]} change={changes[f.key]}
                          onChange={(v) => setField(f, v)} onReset={() => setChanges((c) => ({ ...c, [f.key]: null }))} onUndo={() => drop(f.key)} />
                      </Stack>
                    ))}
                  </Stack>
                </Panel>
              )
            })}
          </Stack>
          <SaveBar count={count} bad={bad} saving={save.isPending} error={save.error} saved={saved} onDiscard={() => { setChanges({}); setSaved(null) }} />
        </form>
      )}
    </Layout>
  )
}

function SaveBar({ count, bad, saving, error, saved, onDiscard }: {
  count: number; bad: boolean; saving: boolean; error: Error | null; saved: string | null; onDiscard: () => void
}) {
  const { t } = useTranslation()
  if (!count && !saved && !error) return null
  return (
    <Paper withBorder radius="lg" p="sm" shadow="md" className="fb-savebar" role="region" aria-label={t('settings.saveBar')}>
      <Group justify="space-between" gap="sm" wrap="wrap">
        <Text size="sm" role="status" aria-live="polite" c={error ? 'down' : saved && !count ? 'up' : undefined}>
          {error ? error.message : count ? t('settings.unsavedCount', { count }) : saved}
        </Text>
        {count > 0 && (
          <Group gap="xs">
            <Button variant="default" onClick={onDiscard}>{t('settings.discard')}</Button>
            <Button type="submit" loading={saving} disabled={bad}>{t('settings.save')}</Button>
          </Group>
        )}
      </Group>
    </Paper>
  )
}
