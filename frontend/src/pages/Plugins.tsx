import { Alert, Anchor, Badge, Button, Group, Loader, Paper, Stack, Switch, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { usePluginLog, usePlugins } from '@/api/queries'
import type { ActionResult, PluginInfo } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

type Result = { ok: boolean; text: string } | null

function PluginLog({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data, error, isPending } = usePluginLog(id, true)
  if (isPending) return <Loader size="sm" aria-label={t('common.loading')} />
  if (error) return <Text className="fb-tone-err">✕ {error.message}</Text>
  return <pre className="fb-log">{data.lines.length ? data.lines.map((l) => `${l.time}  ${l.line}`).join('\n') : t('plugins.emptyLog')}</pre>
}

export function PluginCard({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [result, setResult] = useState<Result>(null)
  const [showLog, setShowLog] = useState(false)
  const done = (ok: boolean, text: string) => setResult({ ok, text })

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => put<{ plugins: PluginInfo[] }>(`/api/settings/plugins/${encodeURIComponent(plugin.id)}`, { enabled }),
    onSuccess: (data, enabled) => {
      client.setQueryData(qk.plugins, { plugins: data.plugins })
      void client.invalidateQueries({ queryKey: qk.dashboard })
      done(true, t(enabled ? 'plugins.turnedOn' : 'plugins.turnedOff', { name: plugin.name }))
    },
    onError: (e) => done(false, e.message),
  })
  const test = useMutation({
    mutationFn: () => post<{ ok: boolean; message: string }>(`/api/settings/plugins/${encodeURIComponent(plugin.id)}/test`),
    onSuccess: (r) => done(r.ok, r.message),
    onError: (e) => done(false, e.message),
  })
  const action = useMutation({
    mutationFn: (id: string) => post<ActionResult>(`/api/plugins/${encodeURIComponent(plugin.id)}/actions/${encodeURIComponent(id)}`),
    onSuccess: (r) => done(true, r.message),
    onError: (e) => done(false, e.message),
  })
  const busy = toggle.isPending || test.isPending || action.isPending
  const trust = plugin.trust === 'builtin' || plugin.trust === 'development' ? t(`plugins.trust.${plugin.trust}`) : plugin.trust

  return (
    <Paper withBorder radius="lg" p="lg" component="section" id={`pl-${plugin.id}`}>
      <Stack gap="sm">
        <Group gap="sm" wrap="wrap">
          <Title order={3} fz="lg">
            {plugin.name}
          </Title>
          {plugin.version && (
            <Text size="sm" c="dimmed" ff="monospace">
              v{plugin.version}
            </Text>
          )}
          <Badge variant="light" color={plugin.trust === 'builtin' ? 'bit' : 'warn'}>
            {trust}
          </Badge>
          <Switch
            ml="auto"
            checked={plugin.enabled}
            disabled={!!plugin.error || toggle.isPending}
            onChange={(e) => toggle.mutate(e.currentTarget.checked)}
            label={plugin.enabled ? t('plugins.on') : t('plugins.off')}
            aria-label={`${plugin.name}: ${plugin.enabled ? t('plugins.on') : t('plugins.off')}`}
          />
        </Group>
        {plugin.description && <Text c="dimmed">{plugin.description}</Text>}
        {plugin.error && (
          <Alert color="down" role="alert">
            ✕ {plugin.error}
          </Alert>
        )}
        <Group gap={6} aria-label={t('plugins.uses')} role="list">
          {plugin.uses.map((u) => (
            <Badge key={u.id} variant="outline" color="gray" tt="none" title={u.label} role="listitem">
              {u.id}
            </Badge>
          ))}
        </Group>
        <Group gap="xs" wrap="wrap">
          {plugin.enabled && plugin.has_test && (
            <Button variant="default" disabled={busy} onClick={() => test.mutate()}>
              {t('plugins.test')}
            </Button>
          )}
          {plugin.enabled &&
            plugin.actions.map((a) => (
              <ConfirmButton key={a.id} variant="default" label={a.label} danger={a.danger} title={a.help} disabled={busy} onConfirm={() => action.mutate(a.id)} />
            ))}
          {plugin.settings_section && (
            <Button component="a" variant="default" href={`/settings#sec-${plugin.settings_section}`}>
              {t('plugins.settings')}
            </Button>
          )}
          <Button variant="subtle" color="gray" onClick={() => setShowLog((v) => !v)} aria-expanded={showLog}>
            {showLog ? t('plugins.hideLog') : t('plugins.log')}
          </Button>
        </Group>
        <Text size="sm" role="status" className={result ? (result.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
          {test.isPending ? t('plugins.testing') : action.isPending ? t('common.working') : result ? `${result.ok ? '✓' : '✕'} ${result.text}` : ''}
        </Text>
        {showLog && <PluginLog id={plugin.id} />}
      </Stack>
    </Paper>
  )
}

export default function Plugins() {
  const { t } = useTranslation()
  const { data, error, isPending } = usePlugins()
  return (
    <Layout title={t('plugins.title')} back={{ href: '/settings', label: t('common.settings') }}>
      <PageHead
        title={t('plugins.title')}
        desc={
          <>
            {t('plugins.intro')} <Anchor href="https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/plugins.md">docs/plugins.md</Anchor>
          </>
        }
      />
      {isPending && <Loader aria-label={t('common.loading')} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && (
        <Stack gap="md">
          {data.plugins.length ? data.plugins.map((p) => <PluginCard key={p.id} plugin={p} />) : <Text>{t('plugins.none')}</Text>}
        </Stack>
      )}
    </Layout>
  )
}
