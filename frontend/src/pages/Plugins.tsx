import { Alert, Anchor, Badge, Button, Group, Loader, Paper, SegmentedControl, SimpleGrid, Stack, Switch, Tabs, Text, TextInput, Title } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { usePluginLog, usePlugins } from '@/api/queries'
import type { ActionResult, PluginInfo } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { LoadingState } from '@/components/ui'
import Marketplace from './plugins/Marketplace'

type Result = { ok: boolean; text: string } | null

function PluginLog({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data, error, isPending } = usePluginLog(id, true)
  if (isPending) return <Loader size="sm" aria-label={t('common.loading')} />
  if (error) return <Text className="fb-tone-err">✕ {error.message}</Text>
  return <pre className="fb-log">{data.lines.length ? data.lines.map((l) => `${l.time}  ${l.line}`).join('\n') : t('plugins.emptyLog')}</pre>
}

function useToggle(plugin: PluginInfo, done: (ok: boolean, text: string) => void) {
  const { t } = useTranslation()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => put<{ plugins: PluginInfo[] }>(`/api/settings/plugins/${encodeURIComponent(plugin.id)}`, { enabled }),
    onSuccess: (data, enabled) => {
      client.setQueryData(qk.plugins, { plugins: data.plugins })
      void client.invalidateQueries({ queryKey: qk.dashboard })
      done(true, t(enabled ? 'plugins.turnedOn' : 'plugins.turnedOff', { name: plugin.name }))
    },
    onError: (e) => done(false, e.message),
  })
}

function OnOff({ plugin, toggle }: { plugin: PluginInfo; toggle: ReturnType<typeof useToggle> }) {
  const { t } = useTranslation()
  return (
    <Switch
      ml="auto"
      checked={plugin.enabled}
      disabled={!!plugin.error || toggle.isPending}
      onChange={(e) => toggle.mutate(e.currentTarget.checked)}
      label={plugin.enabled ? t('plugins.on') : t('plugins.off')}
      aria-label={`${plugin.name}: ${plugin.enabled ? t('plugins.on') : t('plugins.off')}`}
    />
  )
}

function describe(plugin: PluginInfo, t: ReturnType<typeof useTranslation>['t']) {
  return plugin.trust === 'builtin'
    ? t([`integrationSettings.plugins.${plugin.id}`, `integrationSettings.sections.plugin-${plugin.id}.desc`], { defaultValue: plugin.description })
    : plugin.description
}

function Badges({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const trust = ['builtin', 'development', 'official', 'community'].includes(plugin.trust) ? t(`plugins.trust.${plugin.trust}`) : plugin.trust
  return (
    <>
      {plugin.version && <Text size="sm" c="dimmed" ff="monospace">v{plugin.version}</Text>}
      <Badge variant="light" color={plugin.trust === 'builtin' || plugin.trust === 'official' ? 'bit' : 'warn'}>{trust}</Badge>
      {plugin.uses.some((u) => u.id === 'agent') && <Badge variant="outline" color="gray">{t('plugins.agent')}</Badge>}
    </>
  )
}

/** The plugin's own page: on/off, test, actions and log. Its settings are below it (PluginSettings.tsx). */
export function PluginCard({ plugin, titled = true }: { plugin: PluginInfo; titled?: boolean }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<Result>(null)
  const [showLog, setShowLog] = useState(false)
  const done = (ok: boolean, text: string) => setResult({ ok, text })
  const toggle = useToggle(plugin, done)
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

  return (
    <Paper withBorder radius="lg" p="lg" component="section" id={`pl-${plugin.id}`}>
      <Stack gap="sm">
        <Group gap="sm" wrap="wrap">
          {titled && <Title order={3} fz="lg">{plugin.name}</Title>}
          <Badges plugin={plugin} />
          <OnOff plugin={plugin} toggle={toggle} />
        </Group>
        {plugin.description && <Text c="dimmed">{describe(plugin, t)}</Text>}
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

/** One line of the list: what it is, whether it's on, and the way to its own page. */
function PluginRow({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<Result>(null)
  const toggle = useToggle(plugin, (ok, text) => setResult({ ok, text }))
  const href = `/settings/plugins/${encodeURIComponent(plugin.id)}`
  return (
    <Paper withBorder radius="lg" p="md" component="li" id={`pl-${plugin.id}`}>
      <Stack gap={6}>
        <Group gap="sm" wrap="wrap">
          <Title order={2} fz="md"><Anchor href={href} inherit>{plugin.name}</Anchor></Title>
          <Badges plugin={plugin} />
          <OnOff plugin={plugin} toggle={toggle} />
        </Group>
        {plugin.description && <Text size="sm" c="dimmed" lineClamp={2}>{describe(plugin, t)}</Text>}
        {plugin.error && <Alert color="down" role="alert" py="xs">✕ {plugin.error}</Alert>}
        <Group gap="xs" justify="space-between" wrap="wrap">
          <Text size="sm" role="status" className={result ? (result.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
            {result ? `${result.ok ? '✓' : '✕'} ${result.text}` : ''}
          </Text>
          <Button component="a" href={href} variant="default" size="xs">
            {plugin.settings_section ? t('plugins.settings') : t('plugins.open')}
          </Button>
        </Group>
      </Stack>
    </Paper>
  )
}

type Show = 'all' | 'on' | 'off'

export default function Plugins() {
  const { t } = useTranslation()
  const { data, error, isPending } = usePlugins()
  const [query, setQuery] = useState('')
  const [show, setShow] = useState<Show>('all')
  // ?tab=marketplace opens the marketplace straight away, e.g. from a link in the docs.
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'marketplace' ? 'marketplace' : 'installed'
  const setTab = (v: string) => setParams(v === 'marketplace' ? { tab: v } : {}, { replace: true })
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  const shown = (data?.plugins ?? []).filter((p) => {
    if (show === 'on' ? !p.enabled : show === 'off' ? p.enabled : false) return false
    const text = `${p.name} ${p.id} ${describe(p, t)}`.toLowerCase()
    return words.every((w) => text.includes(w))
  })
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
      <Tabs value={tab} onChange={(v) => setTab(v === 'marketplace' ? 'marketplace' : 'installed')} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="installed">{t('plugins.installedTitle')}</Tabs.Tab>
          <Tabs.Tab value="marketplace">{t('marketplace.title')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="installed">
          {isPending && <LoadingState />}
          {error && (
            <Alert color="down" role="alert">
              {t('common.error', { message: error.message })}
            </Alert>
          )}
          {data && (
            <Stack gap="md">
              {data.plugins.length > 6 && (
                <Group gap="sm" wrap="wrap">
                  <TextInput leftSection={<IconSearch size={16} />} placeholder={t('plugins.search')} aria-label={t('plugins.search')}
                    value={query} onChange={(e) => setQuery(e.currentTarget.value)} style={{ flex: '1 1 220px' }} maw={360} />
                  <SegmentedControl value={show} onChange={(v) => setShow(v as Show)} aria-label={t('plugins.show')}
                    data={(['all', 'on', 'off'] as Show[]).map((v) => ({ value: v, label: t(`plugins.shown.${v}`) }))} />
                </Group>
              )}
              {!data.plugins.length && <Text>{t('plugins.none')}</Text>}
              {data.plugins.length > 0 && !shown.length && <Text c="dimmed">{t('plugins.noMatch')}</Text>}
              <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" component="ul" className="fb-plain-list">
                {shown.map((p) => <PluginRow key={p.id} plugin={p} />)}
              </SimpleGrid>
            </Stack>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="marketplace">
          <Marketplace />
        </Tabs.Panel>
      </Tabs>
    </Layout>
  )
}
