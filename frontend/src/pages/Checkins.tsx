import { ActionIcon, Alert, Anchor, Badge, Button, Group, Stack, Table, Tabs, Text, TextInput, Tooltip } from '@mantine/core'
import { IconPlugConnectedX, IconRefresh, IconTrash, IconUnlink } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmIcon } from '@/components/ConfirmButton'
import { ApiError, del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { CheckinConflict, CheckinOverview, CrewCheckin, WiredState } from '@/api/types'
import { Layout } from '@/components/Layout'
import { Link } from 'react-router-dom'
import { PageHead } from '@/components/PageHead'
import { StatCard } from '@/components/StatCard'
import { EmptyState, ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { ago } from '@/lib/time'
import { History } from './checkins/History'

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
  const [q, setQ] = useState('')
  const [state, setState] = useState<WiredState | null>(null)
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
  const pick = (s: WiredState) => () => setState((cur) => (cur === s ? null : s))
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
                desc={t(canSettings ? 'crewCheckin.off.desc' : 'crewCheckin.off.askAdmin')}
                action={canSettings && (
                  <Button component={Link} to="/settings/checkin">{t('crewCheckin.off.turnOn')}</Button>
                )} />
            </Panel>
            <History />
          </>
        ) : query.isPending || !d ? <LoadingState /> : (
          <>
            <div className="fb-stat-row">
              <StatCard label={t('crewCheckin.count.checkedIn')} value={num(d.counts.checked_in)}
                sub={t('crewCheckin.count.pins', { used: d.counts.pins - d.counts.unused_pins, total: d.counts.pins })} />
              <StatCard label={t('crewCheckin.count.verified')} value={num(d.counts.verified)} tone={d.counts.verified ? 'up' : undefined}
                sub={t('crewCheckin.count.learned', { count: d.counts.learned })} />
              <StatCard label={t('crewCheckin.count.pending')} value={num(d.counts.pending)}
                sub={t('crewCheckin.count.pendingSub', { count: d.counts.unverified })} tone={d.counts.unverified ? 'warn' : undefined} />
              <StatCard label={t('crewCheckin.count.notWired')} value={num(d.counts.not_wired)} sub={t('crewCheckin.count.notWiredSub')} />
              <StatCard label={t('crewCheckin.count.review')} value={num(d.counts.conflicts)} tone={d.counts.conflicts ? 'warn' : undefined}
                sub={t('crewCheckin.count.reviewSub')} />
            </div>
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
                <Group gap="xs" mb="sm" wrap="wrap">
                  <TextInput aria-label={t('crewCheckin.search')} placeholder={t('crewCheckin.search')} value={q}
                    onChange={(e) => setQ(e.currentTarget.value)} w={260} />
                  {(['pending', 'verified', 'unverified', 'not_wired'] as WiredState[]).map((s) => (
                    <Button key={s} size="xs" variant={state === s ? 'filled' : 'default'} onClick={pick(s)} aria-pressed={state === s}>
                      {t(`crewCheckin.state.${s}`)} · {d.counts[s]}
                    </Button>
                  ))}
                </Group>
                {d.rows.length === 0 ? (
                  <EmptyState title={t('crewCheckin.empty')} desc={t('crewCheckin.emptyDesc')} />
                ) : (
                    <Table striped highlightOnHover className="fb-table-stack">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>{t('crewCheckin.col.seat')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.nick')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.state')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.port')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.ip')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.device')}</Table.Th>
                          <Table.Th>{t('crewCheckin.col.when')}</Table.Th>
                          {canEdit && <Table.Th aria-label={t('crewCheckin.col.actions')} />}
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {rows.map((r) => (
                          <Table.Tr key={r.seat} data-seat={r.seat}>
                            <Table.Td className="fb-stack-inline"><Anchor href={`/plan?seat=${encodeURIComponent(r.seat)}`}>{r.seat}</Anchor></Table.Td>
                            <Table.Td className="fb-stack-inline">{r.username}{r.pin && <Badge size="xs" variant="light" ml={6}>{t('crewCheckin.pin')}</Badge>}</Table.Td>
                            <Table.Td className="fb-stack-inline"><Badge color={STATE_COLOR[r.wired]} variant="light">{t(`crewCheckin.state.${r.wired}`)}</Badge></Table.Td>
                            <Table.Td data-label={t('crewCheckin.col.port')}>
                              <Text size="sm" ff="monospace">{portText(r.port ?? r.learned)}</Text>
                              {r.learned && <Text size="xs" c="dimmed">{t('crewCheckin.learned')}</Text>}
                              {r.area && <Text size="xs" c="dimmed">{t('cables.areaHint', { label: r.area.label })}</Text>}
                            </Table.Td>
                            <Table.Td data-label={t('crewCheckin.col.ip')}><Text size="sm" ff="monospace">{r.ip ?? '–'}</Text>
                              {r.mac && <Text size="xs" c="dimmed" ff="monospace">{r.mac}</Text>}</Table.Td>
                            <Table.Td data-label={t('crewCheckin.col.device')}>{t(`crewCheckin.device.${r.device}`)}</Table.Td>
                            <Table.Td data-label={t('crewCheckin.col.when')}><Text size="sm">{ago(r.checked_in_at, lang)}</Text></Table.Td>
                            {canEdit && (
                              <Table.Td className="fb-stack-actions">
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
                              </Table.Td>
                            )}
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
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
  if (!conflicts.length) return <EmptyState title={t('crewCheckin.reviewEmpty')} desc={t('crewCheckin.reviewEmptyDesc')} />
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
        <EmptyState title={t('crewCheckin.portalEmpty')} desc={t('crewCheckin.portalEmptyDesc')} />
      ) : (
        <>
          <Text size="sm" c="dimmed">{t('crewCheckin.portalLast', { when: ago(last.at, i18n.language), count: last.done })}</Text>
          <Table striped maw={640}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('crewCheckin.col.when')}</Table.Th>
                <Table.Th>{t('crewCheckin.col.agent')}</Table.Th>
                <Table.Th>{t('crewCheckin.col.done')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {portal.fetches.map((f, i) => (
                <Table.Tr key={`${f.at}-${i}`}>
                  <Table.Td>{ago(f.at, i18n.language)}</Table.Td>
                  <Table.Td>{f.agent ?? '–'}</Table.Td>
                  <Table.Td>{f.done}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  )
}
