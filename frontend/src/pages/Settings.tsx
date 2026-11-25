import { Anchor, Badge, CloseButton, Grid, NavLink, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { lazy, Suspense, useMemo, useState, type ComponentType, type LazyExoticComponent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useFeature, usePageList, usePageListSettled } from '@/api/queries'
import { Layout, PageSkeleton } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { PageTabs } from '@bitsandbricks/ui'
import { InPanel } from '@bitsandbricks/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { readBoot } from '@/nav/boot'
import { BackupPanel, Connections, SectionPanel, SettingsForm } from './settings/editor'
import { S3BackupPanel } from './settings/S3Backups'
import { inSettings, k, keys, sectionTitle, useSettingsEditor, type SettingsAnswer, type SettingsEditor } from './settings/model'

export type { SettingsAnswer }

/** The admin pages that live in a Settings tab, by their address under /settings/ and the page
 *  (floorbit/page_index.py) whose permission shows them. */
const PAGES: Record<string, { page: string; title: string; Body: LazyExoticComponent<ComponentType> }> = {
  users: { page: 'users', title: 'users.title', Body: lazy(() => import('./Users')) },
  teams: { page: 'teams', title: 'teams.title', Body: lazy(() => import('./Teams')) },
  'sign-in': { page: 'signIn', title: 'signin.title', Body: lazy(() => import('./SignIn')) },
  api: { page: 'apiTokens', title: 'api.title', Body: lazy(() => import('./ApiTokens')) },
  webhooks: { page: 'webhooks', title: 'webhooks.title', Body: lazy(() => import('./Webhooks')) },
  tenants: { page: 'tenants', title: 'tenants.title', Body: lazy(() => import('./Tenants')) },
  features: { page: 'features', title: 'features.title', Body: lazy(() => import('./Features')) },
  sidebar: { page: 'sidebarSections', title: 'sidebarSections.title', Body: lazy(() => import('./SidebarSections')) },
  audit: { page: 'audit', title: 'audit.title', Body: lazy(() => import('./Audit')) },
}
const STATUS = 'status'

export type TabId = 'general' | 'people' | 'alerts' | 'tenants' | 'system'

/** The tabs, each a list of groups of entries: a settings section (by its id), an admin page
 *  (PAGES) or the status. A section no tab names (a new one) lands in General under Other.
 *  NetBox and LibreNMS are plugins: their settings are on the Plugins page. */
const TABS: { id: TabId; groups: [string, string[]][] }[] = [
  {
    id: 'general', groups: [
      ['event', ['general', 'appearance', 'display', 'floorplan', 'cabling', 'public', 'speedtest']],
      ['sources', ['seats', 'checkin']],
      ['monitoring', ['monitor', 'live', 'attention', 'health', 'power', 'insights', 'syslog', 'metrics']],
    ],
  },
  { id: 'people', groups: [['accounts', ['users', 'teams']], ['access', ['sign-in', 'signin', 'switchtools', 'api']]] },
  { id: 'alerts', groups: [['alerts', ['discord', 'crew', 'webhooks']]] },
  { id: 'tenants', groups: [['tenants', ['tenants']]] },
  { id: 'system', groups: [['system', [STATUS, 'backup', 'cache', 'features', 'sidebar', 'audit']]] },
]
// Sections shown elsewhere: plugins on their own page, NetBox and LibreNMS as plugins too.
const ELSEWHERE = new Set(['netbox', 'librenms'])
const isPluginSection = (id: string) => id.startsWith('plugin-')

type Section = SettingsAnswer['sections'][number]
type Group = { group: string; items: string[] }

/** The tabs this account sees, with the entries it may open: sections when it may change
 *  settings, pages when the server lists them. */
function useTabs(d: SettingsAnswer | undefined, listed: Set<string>, several: boolean) {
  return useMemo(() => {
    const own = (d?.sections ?? []).filter((s) => !isPluginSection(s.id) && !ELSEWHERE.has(s.id))
    const byId = new Map(own.map((s) => [s.id, s]))
    const placed = new Set(TABS.flatMap((tab) => tab.groups.flatMap(([, ids]) => ids)))
    const can = (id: string) => (id in PAGES ? listed.has(PAGES[id].page) : id === STATUS ? !!d : byId.has(id))
    // One tenant (every self-hosted install) has nothing to manage day to day: Tenants is a row
    // under System, where the second one is added, not a tab of its own (#997).
    const layout = several ? TABS : TABS.filter((tab) => tab.id !== 'tenants').map((tab) =>
      tab.id === 'system' ? { ...tab, groups: tab.groups.map(([g, ids]): [string, string[]] => [g, [...ids, 'tenants']]) } : tab)
    const tabs = layout.map((tab) => {
      const groups: Group[] = tab.groups.map(([group, ids]) => ({ group, items: ids.filter(can) }))
      if (tab.id === 'general') {
        const rest = own.map((s) => s.id).filter((id) => !placed.has(id))
        if (rest.length) groups.push({ group: 'other', items: rest })
      }
      return { id: tab.id, groups: groups.filter((g) => g.items.length) }
    }).filter((tab) => tab.groups.length)
    return { tabs, byId }
  }, [d, listed, several])
}

/** Fields whose label, help, env var or section title has every word typed. */
function matches(ed: SettingsEditor, query: string, t: ReturnType<typeof useTranslation>['t']) {
  const d = ed.d
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!d || !words.length) return null
  const sections = new Map(d.sections.map((s) => [s.id, s]))
  const hits = new Map<string, Set<string>>()
  for (const f of d.fields) {
    const s = sections.get(f.section)
    if (!s) continue
    const text = [
      t(keys(`fields.${k(f.key)}.label`), { defaultValue: f.label }),
      f.help ? t(keys(`fields.${k(f.key)}.help`), { defaultValue: f.help }) : '',
      f.label, f.env ?? '', sectionTitle(t, s), s.title,
    ].join(' ').toLowerCase()
    if (words.every((w) => text.includes(w))) {
      if (!hits.has(s.id)) hits.set(s.id, new Set())
      hits.get(s.id)!.add(f.key)
    }
  }
  return d.sections.filter((s) => hits.has(s.id)).map((s) => ({ section: s, only: hits.get(s.id)! }))
}

/** Where a section's settings are edited: plugins and the plugin-run sources on their plugin page. */
const sectionHref = (s: Section) =>
  isPluginSection(s.id) ? `/settings/plugins/${s.id.slice('plugin-'.length)}` : ELSEWHERE.has(s.id) ? `/settings/plugins/${s.id}` : null

/** Settings: one page with tabs (General, People, Alerts, Tenants, System). Each tab lists its
 *  sections and admin pages on the side; the address names the one on screen (/settings/users),
 *  so every old link still opens the right place. A search over every field sits on top. */
export default function Settings() {
  const { t } = useTranslation()
  const wall = useFeature('stats_wall')
  const navigate = useNavigate()
  const { section: param } = useParams()
  // Older links point at a section of the one long page: /settings#sec-floorplan.
  const { hash } = useLocation()
  const wanted = param ?? (hash.startsWith('#sec-') ? hash.slice('#sec-'.length) : undefined)
  const pages = usePageList()
  const listed = useMemo(() => new Set(pages.map((p) => p.id)), [pages])
  // Accounts that may manage people but not settings see the people pages only. Without the
  // list (it failed), try: the server says no if it must.
  const list = usePageListSettled()
  const mayEdit = list.settled && (list.failed || listed.has('settings'))
  const ed = useSettingsEditor({ enabled: mayEdit, keep: inSettings })
  const d = ed.d
  const several = useMemo(() => !!readBoot().tenants, [])
  const { tabs, byId } = useTabs(d, listed, several)
  const [query, setQuery] = useState('')
  const results = matches(ed, query, t)

  const entries = tabs.flatMap((tab) => tab.groups.flatMap((g) => g.items.map((id) => ({ id, tab: tab.id }))))
  const active = entries.find((e) => e.id === wanted) ?? entries[0]
  const tab = tabs.find((x) => x.id === active?.tab)
  // /settings is the first section; an account without settings opens its pages by their own address.
  const hrefOf = (id: string) => (id === entries[0]?.id && byId.has(id) ? '/settings' : `/settings/${id}`)
  const go = (id: string) => { setQuery(''); navigate(hrefOf(id)) }

  const label = (id: string) =>
    id in PAGES ? t(PAGES[id].title) : id === STATUS ? t('settings.nav.status') : sectionTitle(t, byId.get(id) as Section)
  const unsavedIn = (id: string) => (d ? Object.keys(ed.changes).filter((key) => d.fields.find((f) => f.key === key)?.section === id).length : 0)
  const unsavedTab = (id: TabId) => tabs.find((x) => x.id === id)?.groups.reduce((n, g) => n + g.items.reduce((m, i) => m + unsavedIn(i), 0), 0) ?? 0

  const search = d && (
    <TextInput leftSection={<IconSearch size={16} />} placeholder={t('settings.nav.search')} aria-label={t('settings.nav.search')}
      value={query} onChange={(e) => setQuery(e.currentTarget.value)} w={260} size="sm"
      rightSection={query ? <CloseButton size="sm" aria-label={t('settings.nav.clear')} onClick={() => setQuery('')} /> : undefined} />
  )

  const body = (id: string) => {
    if (id in PAGES) {
      const { Body } = PAGES[id]
      return <InPanel.Provider value><Suspense fallback={<PageSkeleton />}><Body /></Suspense></InPanel.Provider>
    }
    return (
      <SettingsForm ed={ed}>
        {id === STATUS ? (
          <>
            {d && <Connections status={d.status} test={ed.test} />}
            <Text size="sm" c="dimmed">
              {t('settings.nav.sourcesMoved')} <Anchor component={Link} to="/settings/plugins">{t('settings.nav.toPlugins')}</Anchor>
            </Text>
            {wall && <Text size="sm" c="dimmed">{t('settings.wall')} <Anchor href="/wall">/wall</Anchor></Text>}
            <Text size="sm" c="dimmed">{t('settings.nav.whereFrom')}</Text>
          </>
        ) : (
          <>
            <SectionPanel ed={ed} section={byId.get(id) as Section} />
            {id === 'backup' && <><BackupPanel /><S3BackupPanel /></>}
          </>
        )}
      </SettingsForm>
    )
  }

  const one = tab && tab.groups.length === 1 && tab.groups[0].items.length === 1
  // The tab title and the breadcrumbs name the part on screen: Settings › Users.
  const title = active && active.id !== entries[0]?.id ? label(active.id) : t('settings.title')
  return (
    <Layout title={title}>
      <PageHead title={t('settings.title')} eyebrow={t('settings.kicker')} actions={search} />
      <ErrorBanner error={mayEdit ? ed.query.error : null} onRetry={() => void ed.query.refetch()} mb="md" />
      {!list.settled || (mayEdit && ed.query.isPending) ? <LoadingState rows={4} /> : !active ? null : results ? (
        <SettingsForm ed={ed}>
          <Text size="sm" c="dimmed" role="status">{t('settings.nav.results', { count: results.reduce((n, r) => n + r.only.size, 0) })}</Text>
          {results.map(({ section, only }) => {
            const href = sectionHref(section)
            return (
              <SectionPanel key={section.id} ed={ed} section={section} only={only}
                title={href ? <Anchor component={Link} to={href} inherit>{sectionTitle(t, section)}</Anchor> : sectionTitle(t, section)} />
            )
          })}
        </SettingsForm>
      ) : (
        <>
          <PageTabs label={t('settings.title')} active={active.tab} onChange={(id) => {
            const first = tabs.find((x) => x.id === id)?.groups[0]?.items[0]
            if (first) go(first)
          }} tabs={tabs.map((x) => ({ id: x.id, label: t(`settings.tabs.${x.id}`), alert: unsavedTab(x.id) ? 'warn' : null }))} />
          <div role="tabpanel" aria-labelledby={`fb-tab-${active.tab}`} className="fb-settings-panel">
            {one ? body(active.id) : (
              <Grid gap="lg">
                <Grid.Col span={{ base: 12, md: 3 }}>
                  <Select hiddenFrom="md" aria-label={t('settings.nav.section')} allowDeselect={false} value={active.id}
                    data={tab!.groups.map((g) => ({ group: t(`settings.nav.groups.${g.group}`), items: g.items.map((id) => ({ value: id, label: label(id) })) }))}
                    onChange={(v) => v && go(v)} />
                  <nav aria-label={t('settings.nav.section')} className="fb-settings-nav">
                    <Stack gap={2} visibleFrom="md">
                      {tab!.groups.map((g) => (
                        <div key={g.group}>
                          {tab!.groups.length > 1 && <Text size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" mt="xs" mb={2}>{t(`settings.nav.groups.${g.group}`)}</Text>}
                          {g.items.map((id) => {
                            const n = unsavedIn(id)
                            return (
                              <NavLink key={id} variant="light" color="bit" py={6} style={{ borderRadius: 8 }} href={hrefOf(id)} label={label(id)}
                                active={id === active.id} aria-current={id === active.id ? 'page' : undefined}
                                onClick={(e) => { e.preventDefault(); go(id) }}
                                rightSection={n ? <Badge size="xs" color="warn" variant="light" aria-label={t('settings.unsavedCount', { count: n })}>{n}</Badge> : undefined} />
                            )
                          })}
                        </div>
                      ))}
                    </Stack>
                  </nav>
                </Grid.Col>
                <Grid.Col span={{ base: 12, md: 9 }}>{body(active.id)}</Grid.Col>
              </Grid>
            )}
          </div>
        </>
      )}
    </Layout>
  )
}
