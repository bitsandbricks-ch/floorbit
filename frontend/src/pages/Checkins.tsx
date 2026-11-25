import { ActionIcon, Alert, Anchor, Badge, Box, Button, Group, Stack, Tabs, Text, Tooltip, VisuallyHidden } from '@mantine/core'
import { IconPlugConnectedX, IconRefresh, IconTrash, IconUnlink } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError, del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { CheckinConflict, CheckinOverview, CrewCheckin, WiredState } from '@/api/types'
import { ConfirmIcon, DataTable, EmptyState, ErrorBanner, FilterBar, LoadingState, PageHead, StatTile, useFilters } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { Link } from 'react-router-dom'
import { Panel } from '@/components/ui'
import { ago } from '@/lib/time'
import { History } from './checkins/History'
import { LookupNote, LookupWindow } from './checkins/LookupWindow'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/seat-mapping.md'
const STATE_COLOR: Record<WiredState, string> = { pending: 'blue', verified: 'up', not_wired: 'gray', unverified: 'warn' }


// Switched off answers 404 with code checkin_disabled; older servers send the 404 without the code.
const off = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.data?.code === 'checkin_disabled')

const portText = (p: { switch: string; port: string } | null) => (p ? `${p.switch} ${p.port}` : '–')

function matches(row: CrewCheckin, q: string): boolean {
  if (!q) return true
  const needle = q.toLowerCase()
  return [row.seat, row.username, row.ip, row.mac, row.port?.switch, row.port?.port]
    .some((v) => v && v.toLowerCase().includes(needle))
}

/** The crew's view of seat check-in (docs/seat-mapping.md): who checked in, whether the background
 *  found their switch port, what needs a look, and what the agents' captive portal API asked. */
export default function Checkins() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const qc = useQueryClient()
  const canEdit = useCan('seats.edit')
  const canSettings = useCan('settings.manage')
  // The shared filter row like every other list, kept in the address (issue #1423).
  const filters = useFilters({ state: 'all' })
  const q = filters.search
  const state = filters.values.state === 'all' ? null : filters.values.state
  const query = useQuery({
    queryKey: qk.checkinOverview,
    queryFn: () => get<CheckinOverview>('/api/checkins/overview'),
    // Switched off is an answer, not a failure worth asking again.
    retry: (n, e) => !off(e) && n < 3,
    // A pending row turns verified within seconds; poll a little while any wait.
    refetchInterval: (qr) => (qr.state.data?.counts.pending ? 5_000 : 30_000),
  })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.checkinOverview })
  useLiveEvent('checkin', refresh)
  useLiveEvent('checkin.verified', refresh)
  useLiveEvent('checkin.removed', refresh)
  const act = useMutation({
    mutationFn: ({ kind, seat }: { kind: 'retry' | 'remove' | 'forget'; seat: string }) => {
      const s = encodeURIComponent(seat)
      if (kind === 'retry') return post(`/api/checkins/${s}/retry`)
      if (kind === 'forget') return del(`/api/checkins/${s}/port`)
      return del(`/api/checkins/${s}`)
    },
    onSuccess: refresh,
  })

  const d = query.data
  const disabled = off(query.error)
  const rows = (d?.rows ?? []).filter((r) => (!state || r.wired === state) && matches(r, q))
  const num = (n: number) => n.toLocaleString(lang)

  return (
    <Layout title={t('crewCheckin.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('crewCheckin.title')} desc={t('crewCheckin.intro')}
        actions={<Button component={Link} to="/seat-walk" variant="default">{t('seatWalk.title')}</Button>} />
      <Stack gap="md">
        {!disabled && <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />}
        <ErrorBanner error={act.error} />
        {d?.verifier.last_error && (
          <Alert color="warn" role="alert">{t('crewCheckin.verifierError', { error: d.verifier.last_error })}</Alert>
        )}
        {disabled ? (
          <>
            <Panel>
              <EmptyState icon={<IconPlugConnectedX size={24} />} title={t('crewCheckin.off.title')}
                description={t(canSettings ? 'crewCheckin.off.desc' : 'crewCheckin.off.askAdmin')}
                action={canSettings && (
                  <Button component={Link} to="/settings/checkin">{t('crewCheckin.off.turnOn')}</Button>
                )} />
            </Panel>
            <History />
          </>
        ) : query.isPending || !d ? <LoadingState rows={3} /> : (
          <>
            <div className="fb-stat-row">
              <StatTile label={t('crewCheckin.count.checkedIn')} value={num(d.counts.checked_in)}
                sub={d.counts.pins ? t('crewCheckin.count.pins', { used: d.counts.pins - d.counts.unused_pins, total: d.counts.pins }) : t('crewCheckin.count.pinsNone')} />
              <StatTile label={t('crewCheckin.count.verified')} value={num(d.counts.verified)} tone={d.counts.verified ? 'ok' : undefined}
                sub={t('crewCheckin.count.learned', { count: d.counts.learned })} />
              <StatTile label={t('crewCheckin.count.pending')} value={num(d.counts.pending)}
                sub={t('crewCheckin.count.pendingSub', { count: d.counts.unverified })} tone={d.counts.unverified ? 'warn' : undefined} />
              <StatTile label={t('crewCheckin.count.notWired')} value={num(d.counts.not_wired)} sub={t('crewCheckin.count.notWiredSub')} />
              <StatTile label={t('crewCheckin.count.review')} value={num(d.counts.conflicts)} tone={d.counts.conflicts ? 'warn' : undefined}
                sub={t('crewCheckin.count.reviewSub')} />
            </div>
            {d.lookups && <LookupWindow w={d.lookups} canEdit={canEdit} onChange={refresh} />}
            <Tabs defaultValue={new URLSearchParams(window.location.search).get('tab') ?? 'checkins'} keepMounted={false}>
              <Tabs.List>
                <Tabs.Tab value="checkins">{t('crewCheckin.tab.checkins', { count: d.rows.length })}</Tabs.Tab>
                <Tabs.Tab value="review">{t('crewCheckin.tab.review', { count: d.conflicts.length })}</Tabs.Tab>
                <Tabs.Tab value="portal">{t('crewCheckin.tab.portal')}</Tabs.Tab>
                <Tabs.Tab value="history">{t('crewCheckin.tab.history')}</Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="history" pt="md">
                <History />
              </Tabs.Panel>
              <Tabs.Panel value="checkins" pt="md">
                <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('crewCheckin.search')} onClear={filters.clear}
                  groups={filters.groups([
                    { key: 'state', label: t('listFilters.state'), options: [
                      { value: 'all', label: t('listFilters.all'), count: d.rows.length },
                      ...(['pending', 'verified', 'unverified', 'not_wired'] as WiredState[])
                        .map((s) => ({ value: s, label: t(`crewCheckin.state.${s}`), count: d.counts[s] })),
                    ] },
                  ])} />
                {d.rows.length === 0 ? (
                  <EmptyState title={t('crewCheckin.empty')} description={t('crewCheckin.emptyDesc')} />
                ) : (
                  <DataTable label={t('crewCheckin.title')} rows={rows} rowKey={(r) => r.seat} defaultSort={{ id: 'seat' }} striped cards
                    empty={<Text c="dimmed">{t('crewCheckin.noMatch')}</Text>}
                    columns={[
                      { id: 'seat', header: t('crewCheckin.col.seat'), card: 'inline', sort: (r) => r.seat,
                        cell: (r) => <Anchor href={`/plan?seat=${encodeURIComponent(r.seat)}`}>{r.seat}</Anchor> },
                      { id: 'nick', header: t('crewCheckin.col.nick'), card: 'inline', sort: (r) => r.username ?? '',
                        cell: (r) => <>{r.username}{r.pin && <Badge size="xs" variant="light" ml={6}>{t('crewCheckin.pin')}</Badge>}</> },
                      { id: 'state', header: t('crewCheckin.col.state'), card: 'inline', sort: (r) => r.wired,
                        cell: (r) => <><Badge color={STATE_COLOR[r.wired]} variant="light">{t(`crewCheckin.state.${r.wired}`)}</Badge>
                          {r.wired !== 'verified' && <LookupNote lookup={r.lookup} />}</> },
                      { id: 'port', header: t('crewCheckin.col.port'), card: 'label', sort: (r) => portText(r.port ?? r.learned), cell: (r) => (
                        <>
                          <Text size="sm" ff="monospace">{portText(r.port ?? r.learned)}</Text>
                          {r.learned && <Text size="xs" c="dimmed">{t('crewCheckin.learned')}</Text>}
                          {r.area && <Text size="xs" c="dimmed">{t('cables.areaHint', { label: r.area.label })}</Text>}
                        </>
                      ) },
                      { id: 'ip', header: t('crewCheckin.col.ip'), card: 'label', sort: (r) => r.ip ?? '', cell: (r) => (
                        <>
                          <Text size="sm" ff="monospace">{r.ip ?? '–'}</Text>
                          {r.mac && <Text size="xs" c="dimmed" ff="monospace">{r.mac}</Text>}
                        </>
                      ) },
                      { id: 'device', header: t('crewCheckin.col.device'), card: 'label', sort: (r) => r.device, cell: (r) => t(`crewCheckin.device.${r.device}`) },
                      { id: 'when', header: t('crewCheckin.col.when'), card: 'label', sort: (r) => r.checked_in_at ?? 0, cell: (r) => ago(r.checked_in_at, lang) },
                      ...(canEdit ? [{ id: 'actions', header: <VisuallyHidden>{t('crewCheckin.col.actions')}</VisuallyHidden>, card: 'actions' as const,
                        cell: (r: CrewCheckin) => (
                          <Group gap={4} wrap="nowrap" justify="flex-end">
                            {(r.wired === 'unverified' || r.wired === 'pending') && (
                              <Tooltip label={t('crewCheckin.retry')}>
                                <ActionIcon variant="subtle" aria-label={t('crewCheckin.retryFor', { seat: r.seat })}
                                  onClick={() => act.mutate({ kind: 'retry', seat: r.seat })}><IconRefresh size={16} /></ActionIcon>
                              </Tooltip>
                            )}
                            <ConfirmIcon tooltip={t('crewCheckin.remove')} label={t('crewCheckin.removeFor', { seat: r.seat })}
                              onConfirm={() => act.mutate({ kind: 'remove', seat: r.seat })}><IconTrash size={16} /></ConfirmIcon>
                          </Group>
                        ) }] : []),
                    ]} />
                )}
              </Tabs.Panel>
              <Tabs.Panel value="review" pt="md">
                <Review conflicts={d.conflicts} canEdit={canEdit} onForget={(seat) => act.mutate({ kind: 'forget', seat })} />
              </Tabs.Panel>
              <Tabs.Panel value="portal" pt="md">
                <Portal portal={d.portal} />
              </Tabs.Panel>
            </Tabs>
            <Text size="xs" c="dimmed">{t('crewCheckin.footer')} <Anchor href={DOCS} size="xs">docs/seat-mapping.md</Anchor></Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}

function Review({ conflicts, canEdit, onForget }: { conflicts: CheckinConflict[]; canEdit: boolean; onForget: (seat: string) => void }) {
  const { t } = useTranslation()
  if (!conflicts.length) return <EmptyState title={t('crewCheckin.reviewEmpty')} description={t('crewCheckin.reviewEmptyDesc')} />
  return (
    <Stack gap="xs">
      {conflicts.map((c) => (
        <Panel key={`${c.kind}-${c.seat}-${c.port}`} padding="sm">
          <Group justify="space-between" wrap="nowrap">
            <div>
              <Text fw={600}>{t(`crewCheckin.conflict.${c.kind}`, { seat: c.seat, other: c.other.join(', ') })}</Text>
              <Text size="sm" c="dimmed" ff="monospace">{c.switch} {c.port}</Text>
              <Text size="sm" c="dimmed">{t(`crewCheckin.conflictHelp.${c.kind}`)}</Text>
            </div>
            {canEdit && (
              <Group gap="xs" wrap="nowrap">
                {/* On a shared port either seat may be the wrong one: the crew decides after walking over. */}
                {(c.kind === 'shared' ? [c.seat, ...c.other] : [c.seat]).map((seat) => (
                  <Button key={seat} size="xs" variant="default" leftSection={<IconUnlink size={14} />} onClick={() => onForget(seat)}>
                    {t('crewCheckin.forget', { seat })}
                  </Button>
                ))}
              </Group>
            )}
          </Group>
        </Panel>
      ))}
    </Stack>
  )
}

function Portal({ portal }: { portal: CheckinOverview['portal'] }) {
  const { t, i18n } = useTranslation()
  const last = portal.fetches[0]
  return (
    <Stack gap="sm">
      <Text size="sm">{t('crewCheckin.portalIntro')}</Text>
      {!portal.public_url && <Alert color="warn">{t('crewCheckin.portalNoUrl')}</Alert>}
      {!last ? (
        <EmptyState title={t('crewCheckin.portalEmpty')} description={t('crewCheckin.portalEmptyDesc')} />
      ) : (
        <>
          <Text size="sm" c="dimmed">{t('crewCheckin.portalLast', { when: ago(last.at, i18n.language), count: last.done })}</Text>
          <Box maw={640}>
            <DataTable rows={portal.fetches} rowKey={(f, i) => `${f.at}-${i}`} label={t('crewCheckin.tab.portal')} urlState={false}
              pageSize={20} striped density="compact"
              columns={[
                { id: 'when', header: t('crewCheckin.col.when'), cell: (f) => ago(f.at, i18n.language) },
                { id: 'agent', header: t('crewCheckin.col.agent'), cell: (f) => f.agent ?? '–' },
                { id: 'done', header: t('crewCheckin.col.done'), numeric: true, cell: (f) => f.done },
              ]} />
          </Box>
        </>
      )}
    </Stack>
  )
}
