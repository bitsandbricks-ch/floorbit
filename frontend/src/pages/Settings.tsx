import { Anchor, Badge, CloseButton, Grid, Kbd, NavLink, Select, Stack, Text, TextInput } from '@mantine/core'
import { useHotkeys } from '@mantine/hooks'
import {
  IconAdjustmentsHorizontal, IconAlertTriangle, IconArmchair, IconBell, IconBolt, IconBuildingCommunity, IconCalendarEvent,
  IconCircleCheck, IconCircleDashed, IconDatabase, IconDeviceDesktopAnalytics, IconHistory, IconKey, IconLayoutSidebar,
  IconLogin, IconMap, IconSearch, IconServer, IconSettings, IconTerminal2, IconToggleRight, IconUsers, IconUsersGroup,
  IconWebhook, IconWorld, type Icon,
} from '@tabler/icons-react'
import { lazy, Suspense, useMemo, useRef, useState, type ComponentType, type LazyExoticComponent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useFeature, usePageList, usePageListSettled } from '@/api/queries'
import { Layout, PageSkeleton } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { InPanel } from '@bitsandbricks/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { BackupPanel, Connections, SectionPanel, SettingsForm } from './settings/editor'
import { S3BackupPanel } from './settings/S3Backups'
import { useChecklist } from './setup/checklist'
import './Settings.css'
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

/** The left list (#1433, the round-5 H-2 mock): four groups of entries. An entry shows one or
 *  more settings sections (stacked; ``only`` keeps some of a section's fields), an admin page
 *  (PAGES) or the status. Its address is /settings/<entry>, and every section's old address
 *  (/settings/checkin) opens the entry that holds it. A section no entry names (a new one) lands
 *  under Floorbit as its own entry. NetBox and LibreNMS are plugins: their settings are on the
 *  Plugins page. ``step``: the setup checklist step whose state the entry shows. */
export type GroupId = 'event' | 'people' | 'alerts' | 'floorbit'
/** ``only`` / ``except``: some of a section's fields (General feeds two entries). */
type Part = { section: string; only?: string[]; except?: string[] }
type EntryDef = { id: string; icon: Icon; parts?: Part[]; step?: string }
const GENERAL_INVENTORY = ['integrations.inventory_sync_minutes', 'integrations.discovery_minutes']
const GROUPS: { id: GroupId; entries: EntryDef[] }[] = [
  {
    id: 'event', entries: [
      { id: 'appearance', icon: IconCalendarEvent, parts: [{ section: 'appearance' }, { section: 'display' }], step: 'event' },
      { id: 'inventory', icon: IconServer, parts: [{ section: 'general', only: GENERAL_INVENTORY }], step: 'inventory' },
      { id: 'monitor', icon: IconDeviceDesktopAnalytics, step: 'monitoring', parts: ['monitor', 'live', 'attention', 'health', 'insights', 'syslog', 'metrics'].map((section) => ({ section })) },
      { id: 'floorplan', icon: IconMap, parts: [{ section: 'floorplan' }, { section: 'cabling' }], step: 'floor' },
      { id: 'checkin', icon: IconArmchair, parts: [{ section: 'checkin' }, { section: 'seats' }], step: 'seats' },
      { id: 'power', icon: IconBolt, parts: [{ section: 'power' }] },
      { id: 'switchtools', icon: IconTerminal2, parts: [{ section: 'switchtools' }] },
      { id: 'public', icon: IconWorld, parts: [{ section: 'public' }, { section: 'speedtest' }] },
    ],
  },
  {
    id: 'people', entries: [
      { id: 'users', icon: IconUsers, step: 'crew' },
      { id: 'teams', icon: IconUsersGroup },
      { id: 'sign-in', icon: IconLogin, parts: [{ section: 'signin' }] },
      { id: 'api', icon: IconKey },
    ],
  },
  {
    id: 'alerts', entries: [
      { id: 'discord', icon: IconBell, parts: [{ section: 'discord' }, { section: 'crew' }], step: 'alerts' },
      { id: 'webhooks', icon: IconWebhook },
    ],
  },
  {
    id: 'floorbit', entries: [
      { id: 'backup', icon: IconDatabase, parts: [{ section: 'backup' }] },
      { id: 'tenants', icon: IconBuildingCommunity },
      { id: STATUS, icon: IconAdjustmentsHorizontal, parts: [{ section: 'cache' }, { section: 'general', except: GENERAL_INVENTORY }] },
      { id: 'features', icon: IconToggleRight },
      { id: 'sidebar', icon: IconLayoutSidebar },
      { id: 'audit', icon: IconHistory },
    ],
  },
]
// Sections shown elsewhere: plugins on their own page, NetBox and LibreNMS as plugins too.
const ELSEWHERE = new Set(['netbox', 'librenms'])
const isPluginSection = (id: string) => id.startsWith('plugin-')

type Section = SettingsAnswer['sections'][number]
export type Entry = EntryDef & { group: GroupId; parts: Part[] }

/** The entries this account sees: sections when it may change settings, pages when the server
 *  lists them. Tenants only once a second tenant exists or may be added (#997): it sits under
 *  Floorbit either way. */
function useEntries(d: SettingsAnswer | undefined, listed: Set<string>) {
  return useMemo(() => {
    const own = (d?.sections ?? []).filter((s) => !isPluginSection(s.id) && !ELSEWHERE.has(s.id))
    const byId = new Map(own.map((s) => [s.id, s]))
    const placed = new Set(GROUPS.flatMap((g) => g.entries.flatMap((e) => (e.parts ?? []).map((p) => p.section))))
    // A part names the fields it shows (``only``), worked out from the answer; a part left with no
    // field is dropped, so an entry never shows an empty panel.
    const resolve = (parts: Part[] = []): Part[] => parts.flatMap((p) => {
      if (!byId.has(p.section)) return []
      if (!p.only && !p.except) return [p]
      const keys = (d?.fields ?? []).filter((f) => f.section === p.section && (p.only ? p.only.includes(f.key) : !p.except!.includes(f.key))).map((f) => f.key)
      return keys.length ? [{ section: p.section, only: keys }] : []
    })
    const entries: Entry[] = []
    for (const g of GROUPS) {
      for (const e of g.entries) {
        if (e.id in PAGES) {
          if (listed.has(PAGES[e.id].page)) entries.push({ ...e, group: g.id, parts: resolve(e.parts) })
          continue
        }
        const parts = resolve(e.parts)
        if (parts.length || (e.id === STATUS && d)) entries.push({ ...e, group: g.id, parts })
      }
      if (g.id === 'floorbit') {
        for (const s of own) if (!placed.has(s.id)) entries.push({ id: s.id, icon: IconSettings, group: g.id, parts: [{ section: s.id }] })
      }
    }
    return { entries, byId }
  }, [d, listed])
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

const STEP_ICON = { done: IconCircleCheck, skipped: IconCircleCheck, look: IconAlertTriangle, todo: IconCircleDashed }
const STEP_COLOR = { done: 'up', skipped: 'gray', look: 'warn', todo: 'gray' }

/** Settings: one page, a grouped list on the side (Event, People, Alerts, Floorbit; #1433) and
 *  the entry on screen beside it. The address names the entry (/settings/users) and every old
 *  section address still opens the right place. The search sits in the top bar instead of the
 *  global one (#1054); Ctrl K still opens "Go to". */
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
  const { entries, byId } = useEntries(d, listed)
  const steps = useChecklist(mayEdit && listed.has('setup')).data?.steps
  const [query, setQuery] = useState('')
  const results = matches(ed, query, t)
  const searchBox = useRef<HTMLInputElement>(null)
  const focusSearch = () => searchBox.current?.focus()
  // "/" on any keyboard: on Swiss and German ones it takes Shift (memory: Mantine matches Shift exactly).
  useHotkeys([['/', focusSearch], ['shift+/', focusSearch], ['shift+7', focusSearch]])

  const active = entries.find((e) => e.id === wanted) ?? entries.find((e) => e.parts.some((p) => p.section === wanted)) ?? entries[0]
  // /settings is the first entry; an account without settings opens its pages by their own address.
  const hrefOf = (id: string) => (id === entries[0]?.id && !(id in PAGES) ? '/settings' : `/settings/${id}`)
  const go = (id: string) => { setQuery(''); navigate(hrefOf(id)) }

  const label = (e: Entry) =>
    e.id in PAGES ? t(PAGES[e.id].title)
      : GROUPS.some((g) => g.entries.some((x) => x.id === e.id)) ? t(`settings.nav.entries.${e.id}`)
        : sectionTitle(t, byId.get(e.id) as Section)
  const unsavedIn = (e: Entry) => (d ? Object.keys(ed.changes).filter((key) => {
    const f = d.fields.find((x) => x.key === key)
    return !!f && e.parts.some((p) => p.section === f.section && (!p.only || p.only.includes(f.key)))
  }).length : 0)
  const stepOf = (e: Entry) => (e.step ? steps?.find((s) => s.id === e.step) : undefined)

  const search = d && (
    <TextInput ref={searchBox} className="fb-settings-search" leftSection={<IconSearch size={16} />} placeholder={t('settings.nav.search')}
      aria-label={t('settings.nav.search')} aria-keyshortcuts="/" value={query} onChange={(e) => setQuery(e.currentTarget.value)} w={280} size="sm"
      onKeyDown={(e) => { if (e.key === 'Escape') setQuery('') }}
      rightSection={query ? <CloseButton size="sm" aria-label={t('settings.nav.clear')} onClick={() => setQuery('')} /> : <Kbd size="xs">/</Kbd>} />
  )

  const body = (e: Entry) => {
    const panels = e.parts.map((p) => (
      <SectionPanel key={`${p.section}-${p.only?.join() ?? ''}`} ed={ed} section={byId.get(p.section) as Section}
        only={p.only ? new Set(p.only) : undefined} folded={!!p.only}
        {...(p.only ? { title: t(`settings.nav.parts.${e.id}`), desc: null } : {})} />
    ))
    if (e.id in PAGES) {
      const { Body } = PAGES[e.id]
      return (
        <Stack gap="lg">
          <InPanel.Provider value><Suspense fallback={<PageSkeleton />}><Body /></Suspense></InPanel.Provider>
          {panels.length > 0 && <SettingsForm ed={ed}>{panels}</SettingsForm>}
        </Stack>
      )
    }
    return (
      <SettingsForm ed={ed}>
        {e.id === STATUS && (
          <>
            {d && <Connections status={d.status} test={ed.test} />}
            <Text size="sm" c="dimmed">
              {t('settings.nav.sourcesMoved')} <Anchor component={Link} to="/settings/plugins">{t('settings.nav.toPlugins')}</Anchor>
            </Text>
            {wall && <Text size="sm" c="dimmed">{t('settings.wall')} <Anchor href="/wall">/wall</Anchor></Text>}
          </>
        )}
        {panels}
        {e.id === 'backup' && <><BackupPanel /><S3BackupPanel /></>}
        {e.id === STATUS && <Text size="sm" c="dimmed">{t('settings.nav.whereFrom')}</Text>}
      </SettingsForm>
    )
  }

  // The tab title and the breadcrumbs name the part on screen: Settings › Users.
  const title = active && active.id !== entries[0]?.id ? label(active) : t('settings.title')
  const shown = GROUPS.map((g) => ({ id: g.id, entries: entries.filter((e) => e.group === g.id) })).filter((g) => g.entries.length)
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
      ) : entries.length === 1 ? body(active) : (
        <Grid gap="lg">
          <Grid.Col span={{ base: 12, md: 3 }}>
            <Select hiddenFrom="md" aria-label={t('settings.nav.section')} allowDeselect={false} value={active.id}
              data={shown.map((g) => ({ group: t(`settings.nav.groups.${g.id}`), items: g.entries.map((e) => ({ value: e.id, label: label(e) })) }))}
              onChange={(v) => v && go(v)} />
            <nav aria-label={t('settings.nav.section')} className="fb-settings-nav">
              <Stack gap={2} visibleFrom="md">
                {shown.map((g, i) => (
                  <div key={g.id} className={i ? 'fb-settings-group' : undefined}>
                    <Text size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" mt="xs" mb={2}>{t(`settings.nav.groups.${g.id}`)}</Text>
                    {g.entries.map((e) => {
                      const n = unsavedIn(e)
                      const step = stepOf(e)
                      const Mark = step ? STEP_ICON[step.state] : null
                      const Icon = e.icon
                      return (
                        <NavLink key={e.id} variant="light" color="bit" py={6} style={{ borderRadius: 8 }} href={hrefOf(e.id)} label={label(e)}
                          leftSection={<Icon size={17} aria-hidden />}
                          active={e.id === active.id} aria-current={e.id === active.id ? 'page' : undefined}
                          onClick={(ev) => { ev.preventDefault(); go(e.id) }}
                          rightSection={n ? <Badge size="xs" color="warn" variant="light" aria-label={t('settings.unsavedCount', { count: n })}>{n}</Badge>
                            : Mark && step ? <Mark size={15} color={`var(--mantine-color-${STEP_COLOR[step.state]}-filled)`}
                              aria-label={t(`setup.check.state.${step.state}`)} role="img" /> : undefined} />
                      )
                    })}
                  </div>
                ))}
              </Stack>
            </nav>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 9 }}><Stack gap="lg">{body(active)}</Stack></Grid.Col>
        </Grid>
      )}
    </Layout>
  )
}
