import { Alert, Anchor, Badge, Button, Group, Paper, Select, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { PluginIcon } from './icon'
import { MARKET_KEY as KEY, useMarketplace } from './market'
import { qk } from '@/api/keys'
import { LoadingState } from '@bitsandbricks/ui'
import { ConfirmButton } from '@bitsandbricks/ui'

/** One version a source offers (floorbit/marketplace.py, ``catalog``). */
export type MarketVersion = {
  version: string
  date: string
  changes: string
  withdrawn: string
  floorbit: string
  compatible: boolean
  why: string
}

/** What a version may touch, from its manifest (floorbit/plugins/__init__.py, ``touches``). */
export type MarketTouches = {
  uses: string[]
  permissions: string[]
  secrets: number
  sends: Record<string, 'aggregate' | 'device'>
  hall_actions: string[]
  credentials: string[]
}

export type MarketPlugin = {
  id: string
  name: string
  icon?: string
  description: string
  author: string
  homepage: string
  source: string
  builtin: boolean
  installed: string | null
  previous: string | null
  error: string
  enabled: boolean
  withdrawn: string
  update: string | null
  best: string | null
  versions: MarketVersion[]
  listed: boolean
  touches?: MarketTouches | null
}

export type MarketSource = { url: string; name: string; generated: string; error: string }
export type MarketCatalog = { source: MarketSource; plugins: MarketPlugin[] }


/** "What it may touch", before it is installed (docs/plugin-spec.md, "Permissions it asks for"). */
export function Touches({ touches }: { touches: MarketTouches }) {
  const { t } = useTranslation()
  const sends = Object.entries(touches.sends)
  const rows: [string, string][] = [
    ['areas', touches.uses.map((u) => t(`marketplace.area.${u}`, { defaultValue: u })).join(', ')],
    ['permissions', touches.permissions.map((p) => t(`teams.permission.${p.replace('.', '_')}`, { defaultValue: p })).join('; ')],
    ['sends', sends.map(([kind, how]) => t(`marketplace.privacy.${how}`, { kind })).join(', ')],
    ['hallActions', touches.hall_actions.join(', ')],
    ['credentials', touches.credentials.map((c) => t(`marketplace.credential.${c}`, { defaultValue: c })).join(', ')],
    ['secrets', touches.secrets ? t('marketplace.secretCount', { count: touches.secrets }) : ''],
  ]
  return (
    <Paper withBorder radius="md" p="xs" bg="var(--mantine-color-body)" component="dl" aria-label={t('marketplace.touches')} m={0}>
      <Text size="xs" fw={600} mb={4}>
        {t('marketplace.touches')}
      </Text>
      {rows
        .filter(([, value]) => value)
        .map(([key, value]) => (
          <Group key={key} gap={6} wrap="nowrap" align="flex-start">
            <Text component="dt" size="xs" c="dimmed" w={200} style={{ flexShrink: 0 }}>
              {t(`marketplace.touch.${key}`)}
            </Text>
            <Text component="dd" size="xs" m={0}>
              {value}
            </Text>
          </Group>
        ))}
    </Paper>
  )
}

function Entry({ plugin }: { plugin: MarketPlugin }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [pick, setPick] = useState<string | null>(null)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const path = `/api/settings/marketplace/${encodeURIComponent(plugin.id)}`
  const after = (text: string) => {
    setResult({ ok: true, text })
    setPick(null)
    void qc.invalidateQueries({ queryKey: KEY })
    void qc.invalidateQueries({ queryKey: qk.plugins })
  }
  const failed = (e: Error) => setResult({ ok: false, text: e.message })
  const install = useMutation({
    mutationFn: (version: string | null) => post<{ version: string }>(path, version ? { version } : {}),
    onSuccess: (r) => after(t('marketplace.installed', { name: plugin.name, v: r.version })),
    onError: failed,
  })
  const rollback = useMutation({
    mutationFn: () => post<{ version: string }>(`${path}/rollback`),
    onSuccess: (r) => after(t('marketplace.rolledBack', { name: plugin.name, v: r.version })),
    onError: failed,
  })
  const remove = useMutation({
    mutationFn: () => del(path),
    onSuccess: () => after(t('marketplace.removed', { name: plugin.name })),
    onError: failed,
  })
  const busy = install.isPending || rollback.isPending || remove.isPending
  const choices = plugin.versions
    .filter((v) => v.version !== plugin.installed)
    .map((v) => ({
      value: v.version,
      disabled: !!v.withdrawn || !v.compatible,
      label: v.withdrawn
        ? t('marketplace.versionWithdrawn', { v: v.version })
        : !v.compatible
          ? t('marketplace.versionTooNew', { v: v.version, needs: v.floorbit })
          : v.version,
    }))
  const notes = plugin.versions.find((v) => v.version === (plugin.update ?? plugin.best))?.changes

  return (
    <Paper withBorder radius="lg" p="md" component="section" aria-labelledby={`mk-${plugin.id}`}>
      <Stack gap="xs">
        <Group gap="sm" wrap="wrap">
          <PluginIcon name={plugin.icon} />
          <Title order={3} fz="lg" id={`mk-${plugin.id}`}>
            {plugin.name}
          </Title>
          {plugin.installed ? (
            <Badge variant="outline" color="gray" tt="none">
              {t('marketplace.runs', { v: plugin.installed })}
            </Badge>
          ) : null}
          {plugin.update && (
            <Badge variant="light" color="cyan" tt="none">
              {t('marketplace.updateTo', { v: plugin.update })}
            </Badge>
          )}
        </Group>
        {plugin.description && <Text c="dimmed">{plugin.description}</Text>}
        {(plugin.author || plugin.homepage) && (
          <Text size="xs" c="dimmed">
            {plugin.author}
            {plugin.author && plugin.homepage ? ' · ' : ''}
            {plugin.homepage && (
              <Anchor href={plugin.homepage} size="xs" target="_blank" rel="noreferrer">
                {plugin.homepage.replace(/^https?:\/\//, '')}
              </Anchor>
            )}
          </Text>
        )}
        {plugin.builtin && <Text size="sm">{t('marketplace.builtin')}</Text>}
        {!plugin.builtin && plugin.touches && <Touches touches={plugin.touches} />}
        {plugin.withdrawn && (
          <Alert color="down" role="alert">
            {t('marketplace.withdrawn', { v: plugin.installed, why: plugin.withdrawn })}
          </Alert>
        )}
        {plugin.installed && plugin.error && (
          <Alert color="down" role="alert">
            ✕ {plugin.error}
          </Alert>
        )}
        {plugin.installed && !plugin.listed && <Text size="sm" c="warn">{t('marketplace.unlisted')}</Text>}
        {notes && (plugin.update || !plugin.installed) && (
          <Text size="xs" c="dimmed" style={{ whiteSpace: 'pre-line' }}>
            {notes}
          </Text>
        )}
        {!plugin.builtin && (
          <Group gap="xs" wrap="wrap" align="flex-end">
            {!plugin.installed && plugin.best && (
              <Button disabled={busy} loading={install.isPending && !pick} onClick={() => install.mutate(null)}>
                {t('marketplace.install', { v: plugin.best })}
              </Button>
            )}
            {plugin.update && (
              <Button disabled={busy} loading={install.isPending && !pick} onClick={() => install.mutate(null)}>
                {t('marketplace.update', { v: plugin.update })}
              </Button>
            )}
            {plugin.previous && (
              <ConfirmButton variant="default" danger disabled={busy} label={t('marketplace.rollback', { v: plugin.previous })}
                question={t('marketplace.rollbackQuestion', { name: plugin.name, v: plugin.previous })} onConfirm={() => rollback.mutate()} />
            )}
            {plugin.installed && (
              <ConfirmButton variant="default" danger disabled={busy} label={t('marketplace.remove')}
                question={t('marketplace.removeQuestion', { name: plugin.name })} onConfirm={() => remove.mutate()} />
            )}
            {choices.length > 0 && (
              <Group gap={6} align="flex-end" wrap="nowrap">
                <Select size="sm" w={200} label={t('marketplace.otherVersion')} placeholder={t('marketplace.pickVersion')}
                  data={choices} value={pick} onChange={setPick} allowDeselect />
                <Button variant="default" disabled={!pick || busy} loading={install.isPending && !!pick} onClick={() => install.mutate(pick)}>
                  {t('marketplace.installThis')}
                </Button>
              </Group>
            )}
          </Group>
        )}
        {result && (
          <Text size="sm" role="status" className={result.ok ? 'fb-tone-ok' : 'fb-tone-err'}>
            {result.ok ? '✓' : '✕'} {result.text}
          </Text>
        )}
      </Stack>
    </Paper>
  )
}

/** The signed plugin index (docs/marketplace.md): install, update, roll back and remove.
 *  ``updates``: only the installed plugins with a newer version (the Plugins page's Updates tab). */
export default function Marketplace({ updates = false }: { updates?: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, error, isPending, isFetching } = useMarketplace()
  const shown = (data?.plugins ?? []).filter((p) => !updates || (p.installed && p.update))
  const refresh = useMutation({
    mutationFn: () => get<MarketCatalog>('/api/settings/marketplace?refresh=1'),
    onSuccess: (fresh) => qc.setQueryData(KEY, fresh),
  })
  return (
    <Stack gap="md" aria-labelledby="mk-title">
      <Group justify="space-between" wrap="wrap">
        <Title order={2} size="h3" id="mk-title">
          {t(updates ? 'marketplace.updatesTitle' : 'marketplace.title')}
        </Title>
        <Button variant="default" size="compact-sm" loading={refresh.isPending || (isFetching && !isPending)} onClick={() => refresh.mutate()}>
          {t('marketplace.refresh')}
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        {t(updates ? 'marketplace.updatesIntro' : 'marketplace.intro')}
      </Text>
      {isPending && <LoadingState rows={3} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data?.source.error && (
        <Alert color="warn" role="alert" title={t('marketplace.officialSource')}>
          {data.source.error}
        </Alert>
      )}
      {data && (shown.length ? shown.map((p) => <Entry key={p.id} plugin={p} />) : <Text>{t(updates ? 'marketplace.noUpdates' : 'marketplace.empty')}</Text>)}
    </Stack>
  )
}
