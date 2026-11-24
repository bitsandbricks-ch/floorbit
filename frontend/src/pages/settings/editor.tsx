import { Alert, Anchor, Badge, Button, Collapse, ColorInput, FileButton, Group, Image, NumberInput, Paper, PasswordInput, Select, SimpleGrid, Stack, Switch, Text, TextInput, ThemeIcon, Tooltip, UnstyledButton } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { IconChevronRight, IconCircleCheck, IconCircleX, IconDownload, IconUpload } from '@tabler/icons-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { contrast } from '@/colorContrast'
import { Panel } from '@/components/ui'
import { dateTime } from '@/lib/time'
import { HEX, invalid, k, keys, sectionTitle, TESTABLE, type Field, type SettingsAnswer, type SettingsEditor, type TestResult, type useTest, type Value } from './model'


export function TestLine({ result }: { result: TestResult | 'running' | null }) {
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

export function Connections({ status, test }: { status: SettingsAnswer['status']; test: ReturnType<typeof useTest> }) {
  const { t } = useTranslation()
  const redis = status.redis ?? { connected: false }
  const where = `${redis.host ?? '?'}:${redis.port ?? '?'}`
  const items: [string, boolean, string][] = [
    ['NetBox', status.netbox_enabled, t(status.netbox_enabled ? 'settings.configured' : 'settings.netboxOff')],
    ['LibreNMS', status.librenms_enabled, t(status.librenms_enabled ? 'settings.configured' : 'settings.librenmsOff')],
    ['Valkey', redis.connected, redis.connected ? where : t('settings.redisOff', { where })],
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

export function BackupPanel() {
  const { t } = useTranslation()
  const [pending, setPending] = useState<{ name: string; backup: Backup } | null>(null)
  const [result, setResult] = useState<TestResult | null>(null)
  const restore = useMutation({
    mutationFn: (b: Backup) => post<{ skipped_settings?: string[]; kept?: string[] }>('/api/settings/backup', b),
    onSuccess: (r) => {
      setPending(null)
      const skipped = r.skipped_settings?.length ? ' ' + t('settings.backup.skipped', { count: r.skipped_settings.length }) : ''
      // A backup from before cabling and power were in it leaves them as they are: say so.
      const kept = r.kept?.length ? ' ' + t('settings.backup.kept') : ''
      setResult({ ok: true, message: t('settings.backup.restored') + skipped + kept })
      // Settings and the theme come from the server with the page, so load it again.
      setTimeout(() => window.location.reload(), kept ? 6000 : 1200)
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
      made: created && !Number.isNaN(created.getTime()) ? t('settings.backup.made', { when: dateTime(created) }) : '',
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

export function FieldRow({ field, info, change, onChange, onReset, onUndo }: {
  field: Field; info: Value; change: unknown; onChange: (v: unknown) => void; onReset: () => void; onUndo: () => void
}) {
  const { t } = useTranslation()
  const dirty = change !== undefined
  const resetting = change === null
  const value = dirty && !resetting ? change : info.value
  const label = t(keys(`fields.${k(field.key)}.label`), { defaultValue: field.label })
  const help = field.help ? t(keys(`fields.${k(field.key)}.help`), { defaultValue: field.help }) : undefined
  const placeholder = field.placeholder ? t(keys(`fields.${k(field.key)}.placeholder`), { defaultValue: field.placeholder }) : undefined
  const error = dirty && !resetting && invalid(field, change) ? t('settings.invalid') : undefined
  // The label and help stand on the left of the row, so the control only needs its id (#994).
  const id = `setting-${field.key.replace(/[^a-z0-9]+/gi, '-')}`
  const helpId = help ? `${id}-help` : undefined
  const common = { id, disabled: resetting, error, 'aria-describedby': helpId, w: '100%' }

  let input: ReactNode
  switch (field.type) {
    case 'bool':
      input = <Switch id={id} disabled={resetting} aria-describedby={helpId} checked={!!value} onChange={(e) => onChange(e.currentTarget.checked)} />
      break
    case 'secret':
      // Saved, but the vault can't open it (the key changed): say so instead of just "not set".
      input = <PasswordInput {...common} autoComplete="new-password" value={typeof change === 'string' ? change : ''}
        error={error ?? (info.unreadable && !dirty ? t('settings.secretUnreadable') : undefined)}
        placeholder={info.is_set ? t('settings.secretSet') : t('settings.secretUnset')} onChange={(e) => onChange(e.currentTarget.value)} />
      break
    case 'int':
      input = <NumberInput {...common} value={value as number} min={field.min} max={field.max} allowDecimal={false}
        rightSection={field.unit ? <Text size="xs" c="dimmed" pr="xs">{t(`settings.unit.${field.unit}`, { defaultValue: field.unit })}</Text> : undefined}
        rightSectionWidth={field.unit ? 70 : undefined}
        onChange={(v) => onChange(v === '' ? '' : Number(v))} />
      break
    case 'choice':
      input = <Select {...common} allowDeselect={false} value={value as string}
        data={(field.options ?? []).map((o) => ({ value: o.value, label: t(`settings.presets.${o.value}`, { defaultValue: o.label }) }))}
        onChange={(v) => v && onChange(v)} />
      break
    case 'color':
      input = <ColorInput {...common} format="hex" eyeDropperButtonProps={{ 'aria-label': t('settings.pickColour') }} value={(value as string) || ''} placeholder={t('settings.derived')}
        onChange={(v) => onChange(v.toLowerCase())} />
      break
    case 'list':
      input = <TextInput {...common} value={((value as string[]) ?? []).join(', ')} placeholder={placeholder}
        onChange={(e) => onChange(e.currentTarget.value.split(',').map((s) => s.trim()).filter(Boolean))} />
      break
    case 'image':
      input = <ImageField label={label} disabled={resetting} value={(value as string) || ''} onChange={onChange} />
      break
    default:
      input = <TextInput {...common} type={field.type === 'url' ? 'url' : 'text'} spellCheck={false} placeholder={placeholder}
        value={(value as string) ?? ''} onChange={(e) => onChange(e.currentTarget.value.trim().replace(/\/+$/, ''))} />
  }

  return (
    <div className="fb-setting-row" data-key={field.key}>
      <div className="fb-setting-about">
        {field.type === 'image' ? <Text size="sm" fw={500}>{label}</Text>
          : <Text component="label" htmlFor={id} size="sm" fw={500}>{label}</Text>}
        {help && <Text id={helpId} size="xs" c="dimmed">{help}</Text>}
        <Group gap="xs" mt={2}>
          {dirty && <Badge size="sm" variant="light" color="warn" tt="none">{t(resetting ? 'settings.willReset' : 'settings.unsaved')}</Badge>}
          {dirty && <Anchor component="button" type="button" size="xs" onClick={onUndo}>{t('settings.undo')}</Anchor>}
          {!dirty && <SourceTag info={info} env={field.env ?? undefined} />}
          {info.source === 'saved' && !dirty && (
            <Anchor component="button" type="button" size="xs" onClick={onReset}>
              {t(field.type === 'secret' ? 'settings.removeSecret' : 'settings.reset')}
            </Anchor>
          )}
        </Group>
      </div>
      <div className="fb-setting-control">{input}</div>
    </div>
  )
}

/** Where a value comes from, said only when it isn't the default; the env var name is for whoever runs the server, so it waits in a tooltip (#992). */
function SourceTag({ info, env }: { info: Value; env?: string }) {
  const { t } = useTranslation()
  if (info.source === 'default') return null
  const text = <Text size="xs" c="dimmed" data-source={info.source}>{t(`settings.source.${info.source}`)}</Text>
  const tip = env && (info.source === 'env' || info.env_set)
    ? t(info.source === 'env' ? 'settings.envTip' : 'settings.envOverridden', { env })
    : null
  return tip ? <Tooltip label={tip} withArrow multiline maw={320}><span tabIndex={0}>{text}</span></Tooltip> : text
}

function ImageField({ label, disabled, value, onChange }: { label: string; disabled: boolean; value: string; onChange: (v: string) => void }) {
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
      <Group gap="sm">
        {value && <Paper withBorder p={4} radius="md"><Image src={value} alt="" h={40} w="auto" fit="contain" /></Paper>}
        <FileButton onChange={pick} accept="image/svg+xml,image/png,image/jpeg,image/webp" disabled={disabled}>
          {(props) => <Button {...props} variant="default" size="xs" aria-label={`${label}: ${t('settings.chooseImage')}`}>{t('settings.chooseImage')}</Button>}
        </FileButton>
        {value && <Button variant="subtle" size="xs" color="down" disabled={disabled} onClick={() => onChange('')}>{t('settings.removeImage')}</Button>}
      </Group>
      {tooBig && <Text size="xs" c="down" role="alert">{t('settings.imageTooBig', { name: label })}</Text>}
    </Stack>
  )
}

export function ThemeHint({ current }: { current: (key: string) => unknown }) {
  const { t } = useTranslation()
  if (current('theme.preset') !== 'custom') return <Text size="sm" c="dimmed">{t('settings.themeHint')}</Text>
  const accent = current('theme.accent') as string
  const bg = (current('theme.background') as string) || '#0b0b0f'
  if (!HEX.test(accent ?? '') || !HEX.test(bg)) return null
  const ratio = contrast(accent, bg)
  const ok = ratio >= 3
  return <TestLine result={{ ok, message: t(ok ? 'settings.contrastOk' : 'settings.contrastLow', { ratio: ratio.toFixed(1) }) }} />
}

/** "N unsaved changes, Discard, Save": the one way pages with settings save (#993). Inside a form it
 *  submits it; ``onSave`` is for editors that sit inside another page's form or none. */
export function SaveBar({ count, bad = false, saving, error = null, saved = null, onDiscard, onSave }: {
  count: number; bad?: boolean; saving: boolean; error?: Error | null; saved?: string | null; onDiscard: () => void; onSave?: () => void
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
            {onSave ? <Button loading={saving} disabled={bad} onClick={onSave}>{t('settings.save')}</Button>
              : <Button type="submit" loading={saving} disabled={bad}>{t('settings.save')}</Button>}
          </Group>
        )}
      </Group>
    </Paper>
  )
}

/** The form around one or more sections, with the save bar at the bottom. */
export function SettingsForm({ ed, children }: { ed: SettingsEditor; children: ReactNode }) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (ed.count && !ed.bad) ed.save.mutate(ed.changes) }} autoComplete="off" noValidate>
      <Stack gap="md" pb={ed.count ? 96 : 0}>{children}</Stack>
      <SaveBar count={ed.count} bad={ed.bad} saving={ed.save.isPending} error={ed.save.error} saved={ed.saved} onDiscard={ed.discard} />
    </form>
  )
}

/** One section's fields; ``only`` limits it to some of them (search results). */
export function SectionPanel({ ed, section, only, title, desc, actions }: {
  ed: SettingsEditor; section: SettingsAnswer['sections'][number]; only?: Set<string>; title?: ReactNode
  /** null leaves the section's description out (a page that already says it, like a plugin's). */
  desc?: ReactNode | null; actions?: ReactNode
}) {
  const { t } = useTranslation()
  const d = ed.d
  if (!d) return null
  const s = section
  const fields = d.fields.filter((f) => f.section === s.id && (!only || only.has(f.key)))
  const basic = fields.filter((f) => !f.advanced)
  const advanced = fields.filter((f) => f.advanced)
  const row = (f: Field, i: number, list: Field[]) => (
    <Stack key={f.key} gap={0}>
      {/* Above the Custom-only colours, which its text ("the colours below") points at. */}
      {s.id === 'appearance' && f.theme === 'custom' && list[i - 1]?.theme !== 'custom' && <ThemeHint current={ed.current} />}
      <FieldRow field={f} info={d.values[f.key]} change={ed.changes[f.key]}
        onChange={(v) => ed.setField(f, v)} onReset={() => ed.reset(f.key)} onUndo={() => ed.drop(f.key)} />
    </Stack>
  )
  return (
    <Panel id={`sec-${s.id}`} title={title ?? sectionTitle(t, s)}
      desc={desc === null ? undefined : desc ?? t(keys(`sections.${s.id}.desc`), { defaultValue: s.description })}
      actions={actions ?? (TESTABLE.has(s.id) && (
        <Button variant="default" size="xs" onClick={() => void ed.test.run(s.id)}>{t('settings.test')}</Button>
      ))}>
      <Stack gap={0} className="fb-setting-rows">
        {TESTABLE.has(s.id) && <TestLine result={ed.test.results[s.id] ?? null} />}
        {basic.map(row)}
      </Stack>
      {advanced.length > 0 && (
        <Advanced count={advanced.length} open={!!only || advanced.some((f) => ed.changes[f.key] !== undefined)} alone={!basic.length}>
          <Stack gap={0} className="fb-setting-rows">{advanced.map(row)}</Stack>
        </Advanced>
      )}
    </Panel>
  )
}

/** A section's server-side values, folded: open when searching or when one of them has an unsaved change.
 *  The agent settings fold theirs the same way, with their own hint. */
export function Advanced({ count, open, alone = false, hint, children }: {
  count: number; open: boolean; alone?: boolean; hint?: string; children: ReactNode
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(false)
  const opened = shown || open
  return (
    <div className={alone ? 'fb-setting-advanced is-alone' : 'fb-setting-advanced'}>
      <UnstyledButton className="fb-setting-advanced-toggle" aria-expanded={opened} onClick={() => setShown(!opened)}>
        <IconChevronRight size={14} className={opened ? 'is-open' : undefined} aria-hidden />
        <Text size="sm" fw={600} component="span">{t('settings.advanced', { count })}</Text>
        <Text size="xs" c="dimmed" component="span">{hint ?? t('settings.advancedHint')}</Text>
      </UnstyledButton>
      <Collapse expanded={opened}>{children}</Collapse>
    </div>
  )
}
