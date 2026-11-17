import { Alert, Anchor, Badge, Button, Group, Paper, Select, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { ConfirmButton } from '@/components/ConfirmButton'
import { LoadingState } from '@/components/ui'

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

export type MarketPlugin = {
  id: string
  name: string
  description: string
  author: string
  homepage: string
  trust: 'official' | 'community'
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
}

export type MarketSource = { url: string; official: boolean; name: string; generated: string; error: string }
export type MarketCatalog = { sources: MarketSource[]; plugins: MarketPlugin[] }

const KEY = ['marketplace'] as const
const TRUST_COLOR = { official: 'bit', community: 'warn' } as const

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
          <Title order={3} fz="lg" id={`mk-${plugin.id}`}>
            {plugin.name}
          </Title>
          <Badge variant="light" color={TRUST_COLOR[plugin.trust]} tt="none">
            {t(`plugins.trust.${plugin.trust}`)}
          </Badge>
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

/** The signed plugin index (docs/marketplace.md): install, update, roll back and remove. */
export default function Marketplace() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, error, isPending, isFetching } = useQuery({
    queryKey: KEY,
    queryFn: () => get<MarketCatalog>('/api/settings/marketplace'),
  })
  const refresh = useMutation({
    mutationFn: () => get<MarketCatalog>('/api/settings/marketplace?refresh=1'),
    onSuccess: (fresh) => qc.setQueryData(KEY, fresh),
  })
  return (
    <Stack gap="md" aria-labelledby="mk-title">
      <Group justify="space-between" wrap="wrap">
        <Title order={2} size="h3" id="mk-title">
          {t('marketplace.title')}
        </Title>
        <Button variant="default" size="compact-sm" loading={refresh.isPending || (isFetching && !isPending)} onClick={() => refresh.mutate()}>
          {t('marketplace.refresh')}
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        {t('marketplace.intro')}
      </Text>
      {isPending && <LoadingState />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data?.sources
        .filter((s) => s.error)
        .map((s) => (
          <Alert key={s.url} color="warn" role="alert" title={s.official ? t('marketplace.officialSource') : s.url}>
            {s.error}
          </Alert>
        ))}
      {data && (data.plugins.length ? data.plugins.map((p) => <Entry key={p.id} plugin={p} />) : <Text>{t('marketplace.empty')}</Text>)}
      {data && data.sources.length > 1 && (
        <Text size="xs" c="dimmed">
          {t('marketplace.sources', { list: data.sources.map((s) => s.name || s.url).join(', ') })}
        </Text>
      )}
    </Stack>
  )
}
