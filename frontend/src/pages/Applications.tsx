import { Badge, Button, Group, SegmentedControl, Select, SimpleGrid, Stack, TagsInput, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import {
  APPLICATIONS_URL, removeApplication, saveApplication,
  type AppKind, type Application, type ApplicationBody, type ApplicationsAnswer,
} from '@/api/applications'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import {
  ConfirmButton, DataTable, EmptyState, ErrorBanner, FilterBar, PageHead, PanelField, PanelSection, SidePanel,
  type DataColumn,
} from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { bytes } from './traffic/format'

const HOURS = 24
const KIND_COLOR: Record<AppKind, string> = { game: 'teal', launcher: 'cyan', sitegroup: 'grape' }
type Shown = 'all' | AppKind

/** Everything Floorbit recognises in DNS, traffic and the LAN cache (docs/applications.md): games,
 *  launchers and site groups, built in and the event's own, with what each source saw today. */
export default function Applications() {
  const { t } = useTranslation()
  const canEdit = useCan('settings.manage')
  const q = useQuery({ queryKey: qk.applications(HOURS), queryFn: () => get<ApplicationsAnswer>(`${APPLICATIONS_URL}?hours=${HOURS}`) })
  const [shown, setShown] = useState<Shown>('all')
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState<string | null>(null)   // an id, or 'new'
  const apps = q.data?.applications ?? []
  const needle = search.trim().toLowerCase()
  const rows = apps.filter((a) => (shown === 'all' || a.kind === shown)
    && (!needle || a.name.toLowerCase().includes(needle) || a.sites.some((s) => s.includes(needle))))
  const names = Object.fromEntries(apps.map((a) => [a.id, a.name]))
  const count = (k: Shown) => (k === 'all' ? apps.length : apps.filter((a) => a.kind === k).length)
  const index = rows.findIndex((a) => a.id === open)
  const current = open === 'new' ? null : apps.find((a) => a.id === open)

  const columns: DataColumn<Application>[] = [
    { id: 'name', header: t('applications.col.name'), sort: (a) => a.name.toLowerCase(),
      cell: (a) => <Text size="sm" fw={600} c={a.hidden ? 'dimmed' : undefined}>{a.name}</Text> },
    { id: 'kind', header: t('applications.col.kind'), sort: (a) => a.kind, card: 'inline',
      cell: (a) => <Badge variant="light" color={KIND_COLOR[a.kind]} tt="none">{t(`applications.kind.${a.kind}`)}</Badge> },
    { id: 'part', header: t('applications.col.partOf'), hideOnPhone: true, sort: (a) => (a.part_of ? names[a.part_of] ?? a.part_of : ''),
      cell: (a) => <Text size="sm" c="dimmed">{a.part_of ? names[a.part_of] ?? a.part_of : '–'}</Text> },
    { id: 'matches', header: t('applications.col.matches'), hideOnPhone: true, wrap: true,
      cell: (a) => <Text size="sm" c="dimmed">{matchText(t, a)}</Text> },
    { id: 'seats', header: t('applications.col.seats'), numeric: true, descFirst: true, sort: (a) => a.seen.seats,
      cell: (a) => (a.seen.seats ? a.seen.seats : '–') },
    { id: 'bytes', header: t('applications.col.today'), numeric: true, descFirst: true, hideOnPhone: true, sort: (a) => volume(a),
      cell: (a) => (volume(a) ? bytes(volume(a)) : '–') },
    { id: 'source', header: '', hideOnPhone: true,
      cell: (a) => <Text size="xs" c="dimmed">{origin(t, a)}</Text> },
  ]

  return (
    <Layout title={t('applications.title')}>
      <PageHead title={t('applications.title')} desc={t('applications.intro')}
        actions={canEdit ? <Button onClick={() => setOpen('new')}>{t('applications.add')}</Button> : undefined} />
      <Stack gap="md">
        {q.error && <ErrorBanner error={q.error} />}
        <FilterBar search={search} onSearchChange={setSearch} searchLabel={t('applications.search')}
          groups={[{
            key: 'kind', label: t('applications.col.kind'), value: shown, defaultValue: 'all',
            onChange: (v) => setShown(v as Shown),
            options: (['all', 'game', 'launcher', 'sitegroup'] as Shown[]).map((k) => ({
              value: k, label: k === 'all' ? t('applications.all') : t(`applications.kinds.${k}`), count: count(k),
            })),
          }]} />
        <DataTable rows={rows} columns={columns} rowKey={(a) => a.id} label={t('applications.title')}
          loading={q.isLoading} defaultSort={{ id: 'seats', desc: true }} cards urlState
          onRowClick={(a) => setOpen(a.id)}
          selected={open}
          count={(n) => t('applications.count', { count: n })}
          empty={<EmptyState title={t('applications.none')} />} />
        {q.data && (
          <Text size="xs" c="dimmed">
            {t('applications.sources')}{' '}
            {q.data.sources.map((s) => `${s.repo} (${s.license}, ${s.commit.slice(0, 7)})`).join(', ')}
          </Text>
        )}
      </Stack>
      {open && (open === 'new' || current) && (
        <AppPanel key={open} app={current ?? null} apps={apps} canEdit={canEdit} onClose={() => setOpen(null)}
          onSaved={(id) => setOpen(id)}
          onPrev={index > 0 ? () => setOpen(rows[index - 1].id) : undefined}
          onNext={index >= 0 && index < rows.length - 1 ? () => setOpen(rows[index + 1].id) : undefined} />
      )}
    </Layout>
  )
}

function volume(a: Application) {
  return (a.seen.cache_hit_bytes ?? 0) + (a.seen.cache_miss_bytes ?? 0) + (a.seen.traffic_bytes ?? 0)
}

type T = ReturnType<typeof useTranslation>['t']

function matchText(t: T, a: Application) {
  const parts = [
    a.sites.length && t('applications.match.sites', { count: a.sites.length }),
    a.ports.length && t('applications.match.ports', { count: a.ports.length }),
    a.cidr.length && t('applications.match.cidr', { count: a.cidr.length }),
    a.depots.length && t('applications.match.depots', { count: a.depots.length }),
    a.caches.length && t('applications.match.cache', { name: a.caches.join(', ') }),
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : '–'
}

function origin(t: T, a: Application) {
  if (!a.builtin) return t('applications.origin.own')
  if (a.hidden) return t('applications.origin.hidden')
  return a.edited ? t('applications.origin.edited') : t('applications.origin.builtin')
}

/** One application beside the list: for a built-in one, what the event added and whether it is hidden. */
function AppPanel({ app, apps, canEdit, onClose, onSaved, onPrev, onNext }: {
  app: Application | null; apps: Application[]; canEdit: boolean; onClose: () => void; onSaved: (id: string) => void
  onPrev?: () => void; onNext?: () => void
}) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const builtin = !!app?.builtin
  const [name, setName] = useState(app?.name ?? '')
  const [kind, setKind] = useState<AppKind>(app?.kind ?? 'game')
  const [partOf, setPartOf] = useState<string | null>(app?.part_of ?? null)
  const own = builtin ? app!.added : app
  const [sites, setSites] = useState<string[]>(own?.sites ?? [])
  const [ports, setPorts] = useState<string[]>(own?.ports ?? [])
  const [cidr, setCidr] = useState<string[]>(own?.cidr ?? [])
  const [depots, setDepots] = useState<string[]>(own?.depots ?? [])
  const launchers = apps.filter((a) => a.kind === 'launcher').map((a) => ({ value: a.id, label: a.name }))
  const done = (saved?: Application) => {
    void client.invalidateQueries({ queryKey: qk.applicationsAll })
    void client.invalidateQueries({ queryKey: qk.gamesAll })
    if (saved) onSaved(saved.id)
    else onClose()
  }
  const body = (hidden?: boolean): ApplicationBody => ({
    sites, ports, cidr, depots, hidden: hidden ?? app?.hidden ?? false,
    ...(builtin ? {} : { name, kind, part_of: kind === 'game' ? partOf : null }),
  })
  const save = useMutation({ mutationFn: (hidden?: boolean) => saveApplication(app?.id ?? null, body(hidden)), onSuccess: done })
  const remove = useMutation({ mutationFn: () => removeApplication(app!.id), onSuccess: () => done() })
  const fixed = (list: string[], added: string[]) => list.filter((v) => !added.includes(v))

  return (
    <SidePanel onClose={onClose} onPrev={onPrev} onNext={onNext} padded={false}
      title={app ? app.name : t('applications.add')}
      eyebrow={app ? `${t(`applications.kind.${app.kind}`)} · ${origin(t, app)}` : undefined}
      resizable={{ storageKey: 'floorbit.applicationPanel.width' }}
      footer={canEdit ? (
        <Group justify="flex-end" gap="xs">
          {builtin && app!.edited && (
            <ConfirmButton variant="subtle" danger label={t('applications.reset')} question={t('applications.resetAsk')}
              onConfirm={() => remove.mutate()} />
          )}
          {app && !builtin && (
            <ConfirmButton variant="subtle" danger label={t('applications.remove')} question={t('applications.removeAsk', { name: app.name })}
              onConfirm={() => remove.mutate()} />
          )}
          {builtin && (
            <Button variant="default" loading={save.isPending} onClick={() => save.mutate(!app!.hidden)}>
              {app!.hidden ? t('applications.show') : t('applications.hide')}
            </Button>
          )}
          <Button loading={save.isPending} onClick={() => save.mutate(undefined)}>{t('applications.save')}</Button>
        </Group>
      ) : undefined}>
      {(save.error || remove.error) && <PanelSection><ErrorBanner error={save.error ?? remove.error} /></PanelSection>}
      {!builtin && (
        <PanelSection>
          <Stack gap="sm">
            <TextInput label={t('applications.name')} value={name} onChange={(e) => setName(e.currentTarget.value)}
              disabled={!canEdit} maxLength={60} required />
            <div>
              <Text size="sm" fw={500} mb={4}>{t('applications.col.kind')}</Text>
              <SegmentedControl value={kind} onChange={(v) => setKind(v as AppKind)} disabled={!canEdit}
                data={(['game', 'launcher', 'sitegroup'] as AppKind[]).map((k) => ({ value: k, label: t(`applications.kind.${k}`) }))} />
            </div>
            {kind === 'game' && (
              <Select label={t('applications.col.partOf')} data={launchers} value={partOf} onChange={setPartOf}
                clearable searchable disabled={!canEdit} />
            )}
          </Stack>
        </PanelSection>
      )}
      {builtin && app!.part_of && (
        <PanelSection><PanelField label={t('applications.col.partOf')}>{apps.find((a) => a.id === app!.part_of)?.name ?? app!.part_of}</PanelField></PanelSection>
      )}
      <PanelSection label={builtin ? t('applications.addedHere') : undefined}>
        <Stack gap="sm">
          <Matches label={t('applications.sites')} help={t('applications.sitesHelp')} fixed={builtin ? fixed(app!.sites, app!.added.sites) : []}
            value={sites} onChange={setSites} placeholder="example.com" disabled={!canEdit} />
          <Matches label={t('applications.ports')} fixed={builtin ? fixed(app!.ports, app!.added.ports) : []}
            value={ports} onChange={setPorts} placeholder="udp/27015" disabled={!canEdit} />
          <Matches label={t('applications.cidr')} fixed={builtin ? fixed(app!.cidr, app!.added.cidr) : []}
            value={cidr} onChange={setCidr} placeholder="198.51.100.0/28" disabled={!canEdit} />
          <Matches label={t('applications.depots')} help={t('applications.depotsHelp')} fixed={builtin ? fixed(app!.depots, app!.added.depots) : []}
            value={depots} onChange={setDepots} placeholder="228988" disabled={!canEdit} />
        </Stack>
      </PanelSection>
      {app && (
        <PanelSection label={t('applications.seenTitle')}>
          <SimpleGrid cols={3} spacing="sm">
            <PanelField label={t('applications.seen.dns')}>{app.seen.dns_seats_max ?? '–'}</PanelField>
            <PanelField label={t('applications.seen.traffic')}>{app.seen.traffic_seats ?? '–'}</PanelField>
            <PanelField label={t('applications.seen.players')}>{app.seen.players ?? '–'}</PanelField>
            <PanelField label={t('applications.seen.bytes')}>{app.seen.traffic_bytes == null ? '–' : bytes(app.seen.traffic_bytes)}</PanelField>
            <PanelField label={t('applications.seen.cache')}>
              {app.seen.cache_hit_bytes == null ? '–' : bytes((app.seen.cache_hit_bytes ?? 0) + (app.seen.cache_miss_bytes ?? 0))}
            </PanelField>
            <PanelField label={t('applications.seen.lookups')}>{app.seen.lookups ?? '–'}</PanelField>
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt="xs">{t('applications.seenNote')}</Text>
        </PanelSection>
      )}
    </SidePanel>
  )
}

/** The built-in matches as fixed chips, then the event's own as an editable list. */
function Matches({ label, help, fixed, value, onChange, placeholder, disabled }: {
  label: string; help?: string; fixed: string[]; value: string[]; onChange: (v: string[]) => void; placeholder: string; disabled: boolean
}) {
  const { t } = useTranslation()
  return (
    <div>
      {fixed.length > 0 && (
        <Group gap={4} mb={4} aria-label={t('applications.builtinMatches', { label })}>
          <Text size="xs" c="dimmed">{label} · {t('applications.origin.builtin')}:</Text>
          {fixed.slice(0, 24).map((v) => <Badge key={v} variant="outline" color="gray" tt="none" ff="monospace">{v}</Badge>)}
          {fixed.length > 24 && <Text size="xs" c="dimmed">{t('applications.more', { count: fixed.length - 24 })}</Text>}
        </Group>
      )}
      <TagsInput label={label} description={help} value={value} onChange={onChange} placeholder={placeholder}
        disabled={disabled} splitChars={[',', ' ']} clearable />
    </div>
  )
}
