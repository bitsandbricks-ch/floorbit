import { Alert, Anchor, Badge, Button, Group, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePlugins } from '@/api/queries'
import type { MissingPlugin, PluginInfo } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { PageTabs } from '@bitsandbricks/ui'
import { usePageTab } from '@/components/pageTab'
import { LoadingState } from '@bitsandbricks/ui'
import BuiltIn from './plugins/BuiltIn'
import Marketplace from './plugins/Marketplace'
import { useMarketplace } from './plugins/market'
import { pluginName } from '@/lib/pluginName'
import { PluginIcon } from './plugins/icon'
import { PluginCard as Card } from './plugins/Card'
import { Meta, OnOff, StateBadge } from './plugins/parts'
import './Plugins.css'
import { describe, useToggle } from './plugins/toggle'

type Result = { ok: boolean; text: string } | null


/** One card of the list, the same slots on each (#1435): name and state at the top, one line on
 *  what it does, then where it comes from and its switch at the foot. */
function PluginRow({ plugin }: { plugin: PluginInfo }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<Result>(null)
  const toggle = useToggle(plugin, (ok, text) => setResult({ ok, text }))
  const href = `/settings/plugins/${encodeURIComponent(plugin.id)}`
  const about = plugin.description ? describe(plugin, t) : ''
  return (
    <Card id={`pl-${plugin.id}`} data-plugin={plugin.id}
      head={<><PluginIcon name={plugin.icon} />
        <Title order={2} fz="md" className="fb-plugin-card-name"><Anchor href={href} inherit>{pluginName(t, plugin.id, plugin.name)}</Anchor></Title></>}
      badge={<StateBadge plugin={plugin} />}
      about={about}
      foot={<><Meta plugin={plugin} /><OnOff plugin={plugin} toggle={toggle} bare /></>}>
      {plugin.error && <Alert color="down" role="alert" py="xs">✕ {plugin.error}</Alert>}
      {result && (
        <Text size="sm" role="status" className={result.ok ? 'fb-tone-ok' : 'fb-tone-err'}>
          {`${result.ok ? '✓' : '✕'} ${result.text}`}
        </Text>
      )}
    </Card>
  )
}

/** A Marketplace plugin whose data is here without it (the LAN cache an agent reads), in the same card. */
function MissingRow({ plugin, onInstall }: { plugin: MissingPlugin; onInstall: () => void }) {
  const { t } = useTranslation()
  return (
    <Card id={`pl-${plugin.id}`} data-plugin={plugin.id}
      head={<><PluginIcon name="storage" />
        <Title order={2} fz="md" className="fb-plugin-card-name"><Anchor href={plugin.href} inherit>{pluginName(t, plugin.id, plugin.name)}</Anchor></Title></>}
      badge={<Badge variant="light" color="gray" tt="none" style={{ flex: 'none' }}>{t('plugins.missing.label')}</Badge>}
      about={t('plugins.missing.text')}
      foot={<><Text size="xs" c="dimmed">{t('plugins.missing.from')}</Text>
        <Button size="xs" variant="default" onClick={onInstall}>{t('plugins.missing.install')}</Button></>} />
  )
}

type Show = 'all' | 'on' | 'off'

export default function Plugins() {
  const { t } = useTranslation()
  const { data, error, isPending } = usePlugins()
  const [query, setQuery] = useState('')
  const [show, setShow] = useState<Show>('all')
  // ?tab=marketplace opens the marketplace straight away, e.g. from a link in the docs.
  const [tab, setTab] = usePageTab(['installed', 'builtin', 'marketplace', 'updates'])
  const updates = (useMarketplace().data?.plugins ?? []).filter((p) => p.installed && p.update).length
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  const shown = (data?.plugins ?? []).filter((p) => {
    if (show === 'on' ? !p.enabled : show === 'off' ? p.enabled : false) return false
    const text = `${p.name} ${pluginName(t, p.id, p.name)} ${p.id} ${describe(p, t)}`.toLowerCase()
    return words.every((w) => text.includes(w))
  })
  return (
    <Layout title={t('plugins.title')}>
      <PageHead
        title={t('plugins.title')}
        eyebrow={t('plugins.kicker')}
        actions={<Button component="a" variant="default" size="xs" href="https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/plugins.md">{t('plugins.docs')}</Button>}
      />
      <PageTabs label={t('plugins.title')} active={tab} onChange={setTab} tabs={[
        { id: 'installed', label: t('plugins.installedTitle'), count: data?.plugins.length ?? null },
        { id: 'builtin', label: t('plugins.builtin.tab') },
        { id: 'marketplace', label: t('marketplace.title') },
        { id: 'updates', label: t('plugins.updates'), count: updates || null, alert: updates ? 'warn' : null },
      ]} />
      <div role="tabpanel" aria-labelledby={`fb-tab-${tab}`}>
        {tab === 'installed' && <>
          {isPending && <LoadingState rows={3} />}
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
                {!words.length && show !== 'on' && (data.missing ?? []).map((m) => (
                  <MissingRow key={m.id} plugin={m} onInstall={() => setTab('marketplace')} />
                ))}
              </SimpleGrid>
            </Stack>
          )}
        </>}
        {tab === 'builtin' && <BuiltIn />}
        {tab === 'marketplace' && <Marketplace />}
        {tab === 'updates' && <Marketplace updates />}
      </div>
    </Layout>
  )
}
