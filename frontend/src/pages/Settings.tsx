import { Anchor, Badge, CloseButton, Grid, NavLink, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPuzzle, IconSearch } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useFeature } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { BackupPanel, Connections, SectionPanel, SettingsForm } from './settings/editor'
import { k, keys, sectionTitle, useSettingsEditor, type SettingsAnswer, type SettingsEditor } from './settings/model'

export type { SettingsAnswer }

const OVERVIEW = 'overview'
// Which group each section is listed under. A section not named here (a new one) goes under Other.
const GROUPS: [string, string[]][] = [
  ['event', [OVERVIEW, 'appearance', 'display', 'floorplan', 'cabling', 'public', 'general']],
  ['sources', ['netbox', 'librenms', 'seats', 'checkin', 'cache']],
  ['monitoring', ['monitor', 'live', 'attention', 'health', 'power', 'insights', 'syslog', 'metrics']],
  ['alerts', ['discord', 'crew']],
  ['access', ['signin', 'switchtools']],
]
const isPluginSection = (id: string) => id.startsWith('plugin-')

type Section = SettingsAnswer['sections'][number]

function useNav(d: SettingsAnswer | undefined) {
  return useMemo(() => {
    const own = (d?.sections ?? []).filter((s) => !isPluginSection(s.id))
    const byId = new Map(own.map((s) => [s.id, s]))
    const placed = new Set<string>()
    const groups = GROUPS.map(([group, ids]) => {
      const items = ids.filter((id) => id === OVERVIEW || byId.has(id))
      items.forEach((id) => placed.add(id))
      return { group, items }
    })
    const rest = own.map((s) => s.id).filter((id) => !placed.has(id))
    if (rest.length) groups.push({ group: 'other', items: rest })
    return { groups: groups.filter((g) => g.items.length), byId }
  }, [d])
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

/** Settings: one page per section, a list of them on the side, and a search over every field.
 *  Plugin settings are on each plugin's page (PluginSettings.tsx). */
export default function Settings() {
  const { t } = useTranslation()
  const wall = useFeature('stats_wall')
  const navigate = useNavigate()
  const { section: param } = useParams()
  // Older links point at a section of the one long page: /settings#sec-floorplan.
  const { hash } = useLocation()
  const wanted = param ?? (hash.startsWith('#sec-') ? hash.slice('#sec-'.length) : undefined)
  const ed = useSettingsEditor()
  const d = ed.d
  const nav = useNav(d)
  const [query, setQuery] = useState('')
  const active = wanted && nav.byId.has(wanted) ? wanted : OVERVIEW
  const results = matches(ed, query, t)

  const label = (id: string) => (id === OVERVIEW ? t('settings.nav.overview') : sectionTitle(t, nav.byId.get(id) as Section))
  const unsavedIn = (id: string) => (d ? Object.keys(ed.changes).filter((key) => d.fields.find((f) => f.key === key)?.section === id).length : 0)
  const go = (id: string) => { setQuery(''); navigate(id === OVERVIEW ? '/settings' : `/settings/${id}`) }

  const search = (
    <TextInput leftSection={<IconSearch size={16} />} placeholder={t('settings.nav.search')} aria-label={t('settings.nav.search')}
      value={query} onChange={(e) => setQuery(e.currentTarget.value)}
      rightSection={query ? <CloseButton size="sm" aria-label={t('settings.nav.clear')} onClick={() => setQuery('')} /> : undefined} />
  )

  return (
    <Layout title={t('settings.title')}>
      <PageHead title={t('settings.title')} desc={t('settings.intro')} />
      <ErrorBanner error={ed.query.error} onRetry={() => void ed.query.refetch()} mb="md" />
      {ed.query.isPending && <LoadingState rows={4} />}
      {d && (
        <Grid gap="lg">
          <Grid.Col span={{ base: 12, md: 3 }}>
            <Stack gap="sm" className="fb-settings-nav">
              {search}
              <Select hiddenFrom="md" aria-label={t('settings.nav.section')} allowDeselect={false} value={active}
                data={nav.groups.map((g) => ({ group: t(`settings.nav.groups.${g.group}`), items: g.items.map((id) => ({ value: id, label: label(id) })) }))}
                onChange={(v) => v && go(v)} />
              <nav aria-label={t('settings.nav.section')}>
                <Stack gap={2} visibleFrom="md">
                  {nav.groups.map((g) => (
                    <div key={g.group}>
                      <Text size="xs" fw={700} c="dimmed" tt="uppercase" px="sm" mt="xs" mb={2}>{t(`settings.nav.groups.${g.group}`)}</Text>
                      {g.items.map((id) => {
                        const n = unsavedIn(id)
                        return (
                          <NavLink key={id} variant="light" color="bit" py={6} style={{ borderRadius: 8 }} href={id === OVERVIEW ? '/settings' : `/settings/${id}`} label={label(id)}
                            active={!results && id === active} aria-current={!results && id === active ? 'page' : undefined}
                            onClick={(e) => { e.preventDefault(); go(id) }}
                            rightSection={n ? <Badge size="xs" color="warn" variant="light" aria-label={t('settings.unsavedCount', { count: n })}>{n}</Badge> : undefined} />
                        )
                      })}
                    </div>
                  ))}
                  <NavLink variant="light" py={6} style={{ borderRadius: 8 }} href="/settings/plugins" label={t('settings.nav.plugins')} leftSection={<IconPuzzle size={16} />} mt="xs" />
                </Stack>
              </nav>
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 9 }}>
            <SettingsForm ed={ed}>
              {results ? (
                <>
                  <Text size="sm" c="dimmed" role="status">{t('settings.nav.results', { count: results.reduce((n, r) => n + r.only.size, 0) })}</Text>
                  {results.map(({ section, only }) => (
                    <SectionPanel key={section.id} ed={ed} section={section} only={only}
                      title={isPluginSection(section.id)
                        ? <Anchor href={`/settings/plugins/${section.id.slice('plugin-'.length)}`} inherit>{sectionTitle(t, section)}</Anchor>
                        : sectionTitle(t, section)} />
                  ))}
                </>
              ) : active === OVERVIEW ? (
                <>
                  {wall && <Text size="sm" c="dimmed">{t('settings.wall')} <Anchor href="/wall">/wall</Anchor></Text>}
                  <Connections status={d.status} test={ed.test} />
                  <BackupPanel />
                  <Text size="sm" c="dimmed">{t('settings.nav.whereFrom')}</Text>
                </>
              ) : (
                <SectionPanel ed={ed} section={nav.byId.get(active) as Section} />
              )}
            </SettingsForm>
          </Grid.Col>
        </Grid>
      )}
    </Layout>
  )
}
