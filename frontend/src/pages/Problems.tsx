import { ActionIcon, Alert, Anchor, Badge, Button, CopyButton, Group, Menu, Stack, Text, Title } from '@mantine/core'
import { IconArrowDown, IconArrowUp, IconBellOff, IconCheck, IconChevronDown, IconChevronRight, IconCopy, IconDots, IconReplace } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useProblems } from '@/api/queries'
import type { Problem } from '@/api/types'
import { type DataColumn, DataTable, ErrorBanner, FilterBar, LoadingState, PageHead, Pager, pageCount, StatTile, StatusBadge, useFilters } from '@bitsandbricks/ui'
import { Layout } from '@/components/Layout'
import { useNowSeconds } from '@/components/useNowSeconds'
import { canReport, problemsText, rank, reportBody } from './problems/format'
import { fold, type Row } from './problems/fold'
import { useFolds } from './problems/folds'
import { MuteDialog } from './problems/MuteDialog'
import { ShutPorts } from './problems/ShutPorts'
import { muteBody, muteHref, muteTarget, type MuteTarget } from './problems/mute'
import { ago, clock } from '@/lib/time'
import './Problems.css'

/** Rows per page: a big event can have dozens of seats with port trouble (issue #1204); long lists
 *  page at 50 (handbook). */
export const PAGE_SIZE = 50
/** Groups per page when grouped (issue #1472): pages count groups, so a group never splits. */
const GROUP_PAGE = 10
/** The chip that shows everything about a seat, whatever its kind. */
const SEATS = 'seats'

/** A mute this close to its end gets a badge, so +30 min is pressed before the alerts come back (issue #266). */
const ENDING_SOON = 10 * 60


type Actions = {
  canMute: boolean; canSwap?: boolean; busy: boolean
  onMute: (p: Problem) => void; onRaise: (p: Problem, on: boolean) => void; onReport?: (p: Problem) => void; onClear: (p: Problem) => void
}

/** What a problem is: its title, where, what it cuts off and its mute. */
function What({ p }: { p: Row }) {
  const { t } = useTranslation()
  if (p.members) return <Members p={p} />
  return (
    <Stack gap={2} style={{ minWidth: 0 }}>
      {/* Its own page: where it is, its incident and where to look next (issue #882). */}
      <Anchor fw={600} size="sm" c="inherit" href={`/problems/${encodeURIComponent(p.id)}`} style={{ overflowWrap: 'anywhere' }}>{p.title}</Anchor>
      {p.where && <Text size="sm" c="dimmed">{p.where}</Text>}
      {/* A link down because the box at its end is (issue #1415). */}
      {p.links && p.links.length > 0 && (
        <Text size="sm" c="down">
          {t('problemGroups.linksDown', { count: p.links.length, names: p.links.map((l) => l.title).join(' · ') })}
        </Text>
      )}
      {p.cause
        ? <Text size="sm" c="down">{t('problems.behindCause', { name: p.cause })}</Text>
        : <Reach p={p} />}
      {p.muted && (
        <Text size="xs" c="dimmed">
          <IconBellOff size={12} style={{ verticalAlign: '-1px' }} aria-hidden="true" />{' '}
          {t('problems.mutedUntil', { time: clock(p.muted.until), who: p.muted.by ?? '?' })}
          {p.muted.reason ? ` · ${p.muted.reason}` : ''}
        </Text>
      )}
    </Stack>
  )
}

/** The seats of a grouped row, on demand (issue #1415). */
function Members({ p }: { p: Row }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const members = p.members ?? []
  const key = `problemGroups.kinds.${p.kind}`
  const title = i18n.exists(`${key}_other`) ? t(key, { count: members.length })
    : t('problemGroups.title', { count: members.length, kind: t(`problems.kind.${p.kind}`) })
  return (
    <Stack gap={2} style={{ minWidth: 0 }}>
      <Text fw={600} size="sm">{title}</Text>
      <Anchor component="button" type="button" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} style={{ alignSelf: 'flex-start' }}>
        {open ? t('problemGroups.hide') : t('problemGroups.show', { count: members.length })}
      </Anchor>
      {open && (
        <Group gap={6} wrap="wrap">
          {members.map((m) => (
            <Anchor key={m.id} size="sm" href={`/problems/${encodeURIComponent(m.id)}`} title={m.where}>{m.seat}</Anchor>
          ))}
        </Group>
      )}
    </Stack>
  )
}

function RowActions({ p, a }: { p: Row; a: Actions }) {
  const { t } = useTranslation()
  if (p.members) return null
  const report = a.onReport && canReport(p) && p.incident === null
  const swap = a.canSwap && p.kind === 'switch' && p.level === 'down' && p.switch_id
  const mute = a.canMute && (!!p.mute_id || p.kind === 'switch') && !p.muted
  const raise = a.canMute && !p.muted && (p.raised || p.priority !== 1)
  const clear = a.canMute && p.clear_id
  return (
    // One line per row: the main actions as buttons, the rest behind "…", so rows keep one height (issue #1415).
    <Group gap={4} justify="flex-end" wrap="nowrap">
      {p.link && <Button size="compact-sm" variant="default" component="a" href={p.link}>{t('problems.open')}</Button>}
      {/* An offline switch becomes an incident in one click, or links the open one (issue #278). */}
      {p.incident && (
        <Button size="compact-sm" variant="subtle" component="a" href={`/incidents/${encodeURIComponent(p.incident)}`}>
          {t('problems.incidentOpen')}
        </Button>
      )}
      {report && (
        <Button size="compact-sm" variant="subtle" onClick={() => a.onReport?.(p)} disabled={a.busy}>{t('problems.report')}</Button>
      )}
      {(swap || mute || raise || clear) && (
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" aria-label={t('problemGroups.more')} disabled={a.busy}><IconDots size={16} /></ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            {mute && <Menu.Item leftSection={<IconBellOff size={14} />} onClick={() => a.onMute(p)}>{t('problems.mute')}</Menu.Item>}
            {/* Ahead of the rest by hand, when the rules don't know it matters more (issue #1364). */}
            {raise && (
              <Menu.Item leftSection={p.raised ? <IconArrowDown size={14} /> : <IconArrowUp size={14} />} onClick={() => a.onRaise(p, !p.raised)}>
                {p.raised ? t('problemPriority.lower') : t('problemPriority.raise')}
              </Menu.Item>
            )}
            {/* A switch that stays down is swapped for a spare, step by step (issue #1060). */}
            {swap && (
              <Menu.Item leftSection={<IconReplace size={14} />} component="a" href={`/switch-swap/${encodeURIComponent(p.switch_id ?? '')}`}>
                {t('problems.swap')}
              </Menu.Item>
            )}
            {/* A LibreNMS alert whose recovery never came (issue #951). */}
            {clear && <Menu.Item onClick={() => a.onClear(p)}>{t('problems.clear')}</Menu.Item>}
          </Menu.Dropdown>
        </Menu>
      )}
    </Group>
  )
}

const GROUPS = ['none', 'kind', 'device', 'hall'] as const
type GroupBy = typeof GROUPS[number]

/** How a grouped list splits: the group of a row, the groups on this page in order, which are folded, and each header. */
interface Groups {
  by: (p: Row) => string
  order: string[]
  folded: string[]
  onFold: (keys: string[]) => void
  head: (key: string, rows: Row[]) => ReactNode
}

function ProblemTable({ rows, actions, now, label, urlState, groups }: {
  rows: Row[]; actions: Actions; now: number; label: string; urlState: boolean; groups?: Groups
}) {
  const { t } = useTranslation()
  const columns: DataColumn<Row>[] = [
    { id: 'level', header: t('problems.col.level'), width: 130, card: 'inline', sort: (p) => rank(p, now),
      cell: (p) => (
        <Stack gap={2} align="flex-start">
          <StatusBadge size="sm" state={p.muted ? 'unknown' : p.level === 'down' ? 'down' : 'warn'} label={t(`problems.kind.${p.kind}`)} />
          {p.priority === 1 && !p.muted && (
            <Text size="xs" fw={600} c="down" title={p.raised ? t('problemPriority.raisedBy', { who: p.raised.by ?? '?' }) : t('problemPriority.urgentWhy')}>
              {p.raised ? t('problemPriority.raised') : t('problemPriority.urgent')}
            </Text>
          )}
        </Stack>
      ) },
    { id: 'what', header: t('problems.col.what'), wrap: true, card: 'inline', sort: (p) => p.title, cell: (p) => <What p={p} /> },
    { id: 'since', header: t('problems.col.since'), width: 140, card: 'label', descFirst: true, sort: (p) => p.since ?? 0,
      cell: (p) => p.since ? <Text size="sm" c="dimmed">{ago(p.since)}</Text> : '' },
    { id: 'actions', header: '', width: 200, card: 'actions', cell: (p) => <RowActions p={p} a={actions} /> },
  ]
  return (
    <DataTable rows={rows} columns={columns} rowKey={(p) => p.id} label={label} cards urlState={urlState}
      defaultSort={{ id: 'level' }} pageSize={groups ? 0 : PAGE_SIZE} minWidth={720}
      groupBy={groups?.by} groupOrder={groups?.order} groupHeader={groups?.head}
      foldable={!!groups} folded={groups?.folded} onFold={groups?.onFold}
      rowProps={(p) => ({ 'aria-label': p.members ? undefined : p.title, className: `fb-problem-row ${p.muted ? 'muted' : p.level}` })}
      count={urlState ? (n) => t('problems.shown', { count: n }) : undefined} />
  )
}

/** The seats a down switch or link cuts off (issue #950): a count, and the names on demand. */
function Reach({ p }: { p: Problem }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const seats = p.seats ?? []
  const behind = p.behind ?? []
  if (!seats.length && !behind.length) return null
  return (
    <Stack gap={2}>
      <Group gap="xs">
        <Text size="sm" fw={500}>
          {[seats.length ? t('problems.seatsAffected', { count: seats.length }) : '',
            behind.length ? t('problems.switchesBehind', { count: behind.length }) : ''].filter(Boolean).join(' · ')}
        </Text>
        {seats.length > 0 && (
          <Anchor component="button" type="button" size="sm" onClick={() => setOpen(o => !o)} aria-expanded={open}>
            {open ? t('problems.hideSeats') : t('problems.showSeats')}
          </Anchor>
        )}
      </Group>
      {open && seats.length > 0 && <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{seats.join(', ')}</Text>}
      {open && behind.length > 0 && <Text size="xs" c="dimmed">{behind.join(', ')}</Text>}
    </Stack>
  )
}


/** The ready-made dashboard with the Wi-Fi view (floorbit/dashboards.py). */
const WIFI_LINK = '/dashboards/view/network'

/** Everything wrong right now, in one list, with mutes for switches and services someone is working on (issues #10, #256). */
export default function Problems() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useProblems()
  const [target, setTarget] = useState<MuteTarget | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const now = useNowSeconds()
  // The filters live in the address, so a reload or a shared link keeps them (issues #276, #883),
  // on one row like every other list (issue #1472).
  const filters = useFilters({ kind: '', level: 'all', group: 'none', tag: '', muted: 'show', incident: 'all' })
  const folds = useFolds()
  const [groupPage, setGroupPage] = useState(1)
  const [groupsPerPage, setGroupsPerPage] = useState(GROUP_PAGE)
  const refresh = () => void client.invalidateQueries({ queryKey: qk.problems })
  useLiveEvent('monitor.poll', refresh)
  useLiveEvent('alerts.changed', refresh)
  useLiveEvent('power.changed', refresh)
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('incident.changed', refresh)

  const mute = useMutation({
    mutationFn: (v: MuteTarget & { minutes: number; reason: string }) =>
      post('/api/alerts/mutes', { ...muteBody(v), minutes: v.minutes, reason: v.reason }),
    onSuccess: () => { setTarget(null); refresh() },
    onError: (e) => setDialogError(e.message),
  })
  const report = useMutation({
    mutationFn: (p: Problem) => post('/api/incidents', reportBody(p)),
    onSuccess: refresh,
  })
  const raise = useMutation({
    mutationFn: (v: { id: string; on: boolean }) => v.on
      ? post('/api/alerts/raised', { problem_id: v.id })
      : del(`/api/alerts/raised/${encodeURIComponent(v.id)}`),
    onSuccess: refresh,
  })
  const clearAlert = useMutation({
    mutationFn: (id: string) => del(`/api/alerts/librenms/${encodeURIComponent(id)}`),
    onSuccess: refresh,
  })
  const unmute = useMutation({
    mutationFn: (id: string) => del(`/api/alerts/mutes/${encodeURIComponent(id)}`),
    onSuccess: refresh,
  })
  // Still at it when the mute nears its end: half an hour more, same reason (issue #264).
  const extend = useMutation({
    mutationFn: (id: string) => patch(`/api/alerts/mutes/${encodeURIComponent(id)}`, { minutes: 30 }),
    onSuccess: refresh,
  })
  const canSwap = useCan('floorplan.edit')
  // Shut ports name seats: the findings' rule (seats.view).
  const canSeePeople = useCan('seats.view')
  const data = list.data
  // Seat and port trouble are problems too (issue #1204): after the rest, so a switch that is down
  // stays on top, newest first among themselves as the server sends them.
  const all: Problem[] = data ? [...data.problems, ...(data.attention ?? [])] : []
  // In the order they first appear, which is worst first.
  const kinds: string[] = [...new Set(all.map((p) => p.kind))]
  const seatCount = all.filter((p) => p.seat).length
  const chips = seatCount && kinds.length > 1 ? [SEATS, ...kinds] : kinds
  // Several types at once (issue #1472): "security,service"; none picked shows every row. A type
  // that is gone from the list stops counting, so an old link doesn't empty the page.
  const picked = filters.values.kind.split(',').filter((k) => chips.includes(k))
  const ofType = (p: Problem) => !picked.length || picked.some((k) => (k === SEATS ? !!p.seat : p.kind === k))
  const level = filters.values.level
  const hideMuted = filters.values.muted === 'hide'
  // Whether someone works on it (#883): only those who see the board get the incident at all.
  const seesIncidents = all.some((p) => p.incident !== undefined)
  const incident = seesIncidents ? filters.values.incident : 'all'
  const worked = (p: Problem) => incident === 'all' || (incident === 'open') === !!p.incident
  // Hall and tag come from the switch's inventory entry, or the seat's block (issue #1364).
  const hallNames = [...new Set(all.map((p) => p.hall).filter((h): h is string => !!h))]
  const tags = [...new Set(all.flatMap((p) => p.tags ?? []))].sort((x, y) => x.localeCompare(y))
  const tag = filters.values.tag
  const groupBy: GroupBy = (GROUPS as readonly string[]).includes(filters.values.group) ? filters.values.group as GroupBy : 'none'
  const query = filters.search.trim().toLowerCase()
  const found = (p: Problem) => !query || [p.title, p.where, p.device, p.seat, p.hall].some((v) => v?.toLowerCase().includes(query))
  const matches = (p: Problem) => ofType(p)
    && (level === 'all' || (level === 'down' ? p.level === 'down' : p.level !== 'down'))
    && !(hideMuted && p.muted) && (!tag || (p.tags ?? []).includes(tag)) && worked(p) && found(p)
  const matching = all.filter(matches).sort((x, y) => rank(x, now) - rank(y, now))
  // The same seat problem on many seats is one row, and a down link hangs under its down box
  // (issue #1415). A kind picked on purpose stays one row per seat.
  const visible = fold(matching, (k) => picked.includes(k) || picked.includes(SEATS))
  const groupKey = (p: Problem) => groupBy === 'kind' ? t(`problems.kind.${p.kind}`) : groupBy === 'hall' ? p.hall ?? '' : p.device ?? ''
  const groups = groupBy === 'none' ? [] : [...new Set(visible.map(groupKey))]
    .sort((x, y) => (x === '' ? 1 : 0) - (y === '' ? 1 : 0) || x.localeCompare(y, undefined, { numeric: true }))
  const foldKey = (g: string) => `${groupBy}:${g}`
  const allFolded = groups.length > 0 && groups.every((g) => folds.isFolded(foldKey(g)))
  // A filter that leaves fewer groups would strand the page past the end.
  const page = Math.min(groupPage, pageCount(groups.length, groupsPerPage))
  const pageGroups = groups.slice((page - 1) * groupsPerPage, page * groupsPerPage)
  const actions: Actions = {
    canMute: !!data?.can_mute, canSwap, busy: mute.isPending || report.isPending || clearAlert.isPending || raise.isPending,
    onReport: data?.can_report ? (p) => report.mutate(p) : undefined,
    onClear: (p) => clearAlert.mutate(p.clear_id ?? ''),
    onMute: (p) => { setDialogError(null); setTarget(muteTarget(p)) },
    onRaise: (p, on) => raise.mutate({ id: p.id, on }),
  }
  const error = list.error ?? unmute.error ?? extend.error ?? report.error ?? clearAlert.error ?? raise.error

  return (
    // Muted problems stay out of the tab count: someone is already on them (issue #214).
    <Layout title={t('problems.title')} back={{ href: '/', label: t('common.floorPlan') }}
      count={data ? data.counts.total ?? (data.counts.down ?? 0) + (data.counts.warn ?? 0) : undefined}>
      <PageHead title={t('problems.title')} desc={t('problems.intro')} actions={data && (
        // For pasting into the crew chat instead of a screenshot (issue #280).
        <CopyButton value={problemsText(matching, data.mutes, t, (ts) => ago(ts))} timeout={2000}>
          {({ copied, copy }) => (
            <Button variant="default" size="xs" leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              color={copied ? 'up' : undefined} onClick={copy}>
              {copied ? t('problems.copied') : t('problems.copy')}
            </Button>
          )}
        </CopyButton>
      )} />
      <ErrorBanner error={error} mb="md" />
      {list.isPending || !data ? (
        <LoadingState rows={3} />
      ) : (
        <Stack gap="md">
          {data.quiet_hours && <Alert color="gray" variant="light">{t('problems.quiet')}</Alert>}
          <div className="fb-stat-row" aria-live="polite">
            {(['down', 'look', 'seats', 'muted'] as const).map((k) => (
              <StatTile key={k} label={t(`problems.card.${k}`)} value={String(data.counts[k] ?? (k === 'look' ? data.counts.warn : 0))}
                tone={data.counts[k] && k !== 'muted' ? (k === 'down' ? 'err' : 'warn') : undefined} />
            ))}
          </div>
          {all.length > 0 && (
            <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('problemHeader.search')} onClear={filters.clear}
              groups={filters.groups([
                { key: 'kind', label: t('problemHeader.type'), multiple: true, hidden: kinds.length < 2, options: chips.map((k) => ({
                  value: k,
                  label: k === SEATS ? t('problems.seats') : t(`problems.kind.${k}`),
                  count: k === SEATS ? seatCount : all.filter((p) => p.kind === k).length,
                })) },
                { key: 'level', label: t('problems.filter.level'), options: (['all', 'down', 'warn'] as const).map((v) => ({
                  value: v, label: t(`problems.filter.levels.${v}`),
                  count: v === 'all' ? all.length : all.filter((p) => (p.level === 'down') === (v === 'down')).length,
                })) },
                { key: 'group', label: t('problems.filter.group'), options: GROUPS.filter((v) => v !== 'hall' || hallNames.length > 1 || groupBy === 'hall')
                  .map((v) => ({ value: v, label: v === 'hall' ? t('problemPriority.groupHall') : t(`problems.filter.groups.${v}`) })) },
                { key: 'tag', label: t('problemPriority.tag'), hidden: !tags.length,
                  options: [{ value: '', label: t('problemHeader.anyTag') }, ...tags.map((v) => ({ value: v, label: v }))] },
                { key: 'incident', label: t('problemIncident.label'), hidden: !seesIncidents, options: (['all', 'open', 'none'] as const).map((v) => ({
                  value: v, label: t(`problemIncident.${v}`),
                  count: v === 'all' ? all.length : all.filter((p) => !!p.incident === (v === 'open')).length,
                })) },
                { key: 'muted', label: t('problemHeader.muted'), options: [
                  { value: 'show', label: t('problemHeader.mutedShown') },
                  { value: 'hide', label: t('problemHeader.mutedHidden'), count: all.filter((p) => !p.muted).length },
                ] },
              ])}
              actions={groups.length > 1 && (
                <Button size="xs" variant="default" leftSection={allFolded ? <IconChevronRight size={14} /> : <IconChevronDown size={14} />}
                  onClick={() => folds.setAll(groups.map(foldKey), !allFolded)}>
                  {allFolded ? t('problemHeader.unfoldAll') : t('problemHeader.foldAll')}
                </Button>
              )} />
          )}
          {!all.length ? (
            <Text c="dimmed">{t('problems.none')}</Text>
          ) : !visible.length ? (
            <Text c="dimmed">{t('problems.noneShown')}</Text>
          ) : groupBy === 'none' ? (
            <ProblemTable rows={visible} actions={actions} now={now} label={t('problems.title')} urlState />
          ) : (
            <>
              {/* One table, a header row per group that folds it away and stays folded across reloads (issue #1472). */}
              <ProblemTable rows={visible.filter((p) => pageGroups.includes(groupKey(p)))} actions={actions} now={now} label={t('problems.title')}
                urlState={false} groups={{
                  by: groupKey, order: pageGroups,
                  folded: pageGroups.filter((g) => folds.isFolded(foldKey(g))),
                  onFold: (keys) => folds.setFolded(pageGroups.map(foldKey), keys.filter((g) => pageGroups.includes(g)).map(foldKey)),
                  head: (g, rows) => {
                    const name = g || (groupBy === 'hall' ? t('problemPriority.noHall') : t(groupBy === 'device' ? 'problems.noDevice' : 'problems.all'))
                    const down = rows.filter((p) => p.level === 'down' && !p.muted).length
                    return (
                      <span className="fb-problem-group-head">
                        <span>{name}</span>
                        <Text span c="dimmed" size="sm" fw={400}>{rows.length}</Text>
                        {down > 0 && <Text span c="down" size="sm" fw={600}>{t('problemHeader.downCount', { count: down })}</Text>}
                      </span>
                    )
                  },
                }} />
              {groups.length > GROUP_PAGE && (
                <Pager page={page} perPage={groupsPerPage} total={groups.length} onPage={setGroupPage}
                  onPerPage={(n) => { setGroupsPerPage(n); setGroupPage(1) }} perPageOptions={[10, 25, 50]}
                  rangeLabel={(from, to, total) => t('problemHeader.groupPages', { from, to, total })} />
              )}
            </>
          )}
          {data.mutes.length > 0 && (
            <section aria-labelledby="muted-switches">
              <Title order={2} size="h4" id="muted-switches" mb="xs">{t('problems.mutes')}</Title>
              <Stack gap={4}>
                {data.mutes.map((m) => (
                  <Group key={m.switch_id} gap="sm">
                    <Text size="sm"><Anchor href={muteHref({ ...m, kind: m.kind ?? 'switch' }, WIFI_LINK)}>{m.name}</Anchor> · {t('problems.mutedUntil', { time: clock(m.until), who: m.by ?? '?' })}{m.reason ? ` · ${m.reason}` : ''}</Text>
                    {m.until - now < ENDING_SOON && (
                      <Badge color="warn" variant="light" tt="none">
                        {t('problems.endsIn', { count: Math.max(1, Math.ceil((m.until - now) / 60)) })}
                      </Badge>
                    )}
                    {data.can_mute && (
                      <Group gap={4}>
                        <Button size="compact-xs" variant="subtle" onClick={() => extend.mutate(m.switch_id)} disabled={extend.isPending}
                          aria-label={t('problems.extendLabel', { name: m.name })}>
                          {t('problems.extend')}
                        </Button>
                        <Button size="compact-xs" variant="subtle" onClick={() => unmute.mutate(m.switch_id)} disabled={unmute.isPending}>
                          {t('problems.unmute')}
                        </Button>
                      </Group>
                    )}
                  </Group>
                ))}
              </Stack>
            </section>
          )}
          {canSeePeople && <ShutPorts always={picked.includes('security')} />}
        </Stack>
      )}
      <MuteDialog target={target} busy={mute.isPending} error={dialogError} onClose={() => setTarget(null)}
        onSave={(minutes, reason) => target && mute.mutate({ ...target, minutes, reason })} />
    </Layout>
  )
}
