import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Text, Tooltip, VisuallyHidden } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import {
  DataTable, FilterBar, PanelField, PanelSection, SidePanel, Sparkline, StatGrid, StatTile, StatusBit, useFilters,
  type DataColumn,
} from '@bitsandbricks/ui'
import { ago } from '@/lib/time'
import { agentHref, groupHref, type AgentRow, type AgentsAnswer } from './data'
import { byTone, FILTERS, groupRows, matches, SHOW, STATE_COLOR, type AgentLoad, type ListGroup, type ListRow, type Role } from './listModel'
import { Blocked } from './Details'
import { HintAnchor } from './HintAnchor'
import { PLUGIN_COLOR, pluginSays, plugins, stateKey, upText } from './model'
import './AgentList.css'

const TONE_BIT = { up: 'ok', warn: 'warn', down: 'err' } as const
const ROLE_COLOR: Record<Role, string> = { primary: 'up', active: 'gray', standby: 'gray', alone: 'gray', offline: 'down' }
const SHOWN_PROBLEMS = 4


/** The Local agents list (issue #1463, option A of the mocks): four figures, search and filters,
 *  then one table grouped by agent group with the problems first; a row opens the agent in a side
 *  panel beside the list. Made for many agents: a hall with forty of them still reads at a glance. */
export function AgentList({ data, rows }: { data: AgentsAnswer; rows: AgentRow[] }) {
  const { t } = useTranslation()
  const load = useQuery({ queryKey: [...qk.agents, 'load'], queryFn: () => get<AgentLoad>('/api/agents/load'), refetchInterval: 60_000 })
  const filters = useFilters(FILTERS)
  const [selected, setSelected] = useState<string | null>(null)
  const show = filters.values.show
  const groups = groupRows(rows, data.groups, data.newest_version, load.data, t('agents.allDevices'))
  const needle = filters.search.trim().toLowerCase()
  const shown = groups
    .filter((g) => filters.values.group === 'any' || g.id === filters.values.group)
    .map((g) => ({ ...g, rows: g.rows.filter((r) => matches(r, show, needle, g.label)) }))
    .filter((g) => g.rows.length)
  const flat = shown.flatMap((g) => g.rows)
  const all = groups.flatMap((g) => g.rows)
  const count = (s: string) => all.filter((r) => matches(r, s, '')).length
  const pickedAt = flat.findIndex((r) => r.agent.id === selected)
  const picked = pickedAt >= 0 ? flat[pickedAt] : null
  const pickedGroup = picked ? shown.find((g) => g.rows.includes(picked)) : undefined
  const step = (by: number) => {
    const next = flat[pickedAt + by]
    if (next) setSelected(next.agent.id)
  }

  return (
    <Stack gap="md">
      <Figures groups={groups} newest={data.newest_version} />
      <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('agentList.search')} onClear={filters.clear}
        groups={filters.groups([
          { key: 'show', label: t('agentList.show'), options: SHOW.map((s) => ({ value: s, label: t(`agentList.filter.${s}`), count: count(s) })) },
          { key: 'group', label: t('agentList.group'), hidden: groups.length < 2, options: [
            { value: 'any', label: t('agentList.anyGroup') },
            ...groups.map((g) => ({ value: g.id, label: g.label, count: g.rows.length })),
          ] },
        ])} />
      {shown.length === 0 ? <Text c="dimmed">{t('agentList.noMatch')}</Text> : (
        <Paper withBorder radius="md" className="fb-agent-list" aria-label={t('agentList.label')}>
          {shown.map((g, i) => (
            <Fragment key={g.id}>
              <GroupHead group={g} />
              <AgentTable group={g} head={i === 0} selected={selected} onSelect={setSelected} newest={data.newest_version} />
            </Fragment>
          ))}
        </Paper>
      )}
      {picked && (
        <AgentPanel row={picked} group={pickedGroup} onClose={() => setSelected(null)}
          onPrev={pickedAt > 0 ? () => step(-1) : undefined} onNext={pickedAt < flat.length - 1 ? () => step(1) : undefined} />
      )}
    </Stack>
  )
}

/** Four figures over every agent: online, need a look, failover ready, up to date. */
function Figures({ groups, newest }: { groups: ListGroup[]; newest?: string | null }) {
  const { t, i18n } = useTranslation()
  const all = groups.flatMap((g) => g.rows)
  const online = all.filter((r) => r.agent.connected)
  const offline = all.filter((r) => !r.agent.connected)
  const look = [...all].sort(byTone).filter((r) => r.tone !== 'up')
  const multi = groups.filter((g) => g.rows.length > 1)
  const ready = multi.filter((g) => g.state === 'ok')
  const versioned = all.filter((r) => r.agent.version)
  const old = versioned.filter((r) => r.old)
  const names = (list: ListRow[]) => list.length > 3
    ? t('agentList.namesMore', { names: list.slice(0, 3).map((r) => r.agent.name).join(', '), count: list.length - 3 })
    : list.map((r) => r.agent.name).join(', ')
  return (
    <StatGrid columns={4}>
      <StatTile label={t('agentList.fig.online')} value={`${online.length} / ${all.length}`}
        tone={offline.length === 0 ? 'ok' : online.length ? 'warn' : 'err'}
        sub={offline.length ? t('agentList.fig.offline', { names: names(offline) }) : t('agentList.fig.allOnline')} />
      <StatTile label={t('agentList.fig.look')} value={look.length.toLocaleString(i18n.language)}
        tone={look.some((r) => r.tone === 'down') ? 'err' : look.length ? 'warn' : undefined}
        sub={look.length ? names(look) : t('agentList.fig.allGood')} />
      <StatTile label={t('agentList.fig.failover')} value={multi.length ? `${ready.length} / ${multi.length}` : '–'}
        tone={multi.length ? (ready.length < multi.length ? 'warn' : 'ok') : undefined}
        sub={multi.length ? t('agentList.fig.failoverSub') : t('agentList.fig.noPairs')} />
      <StatTile label={t('agentList.fig.current')} value={versioned.length ? `${versioned.length - old.length} / ${versioned.length}` : '–'}
        tone={old.length ? 'warn' : versioned.length ? 'ok' : undefined}
        sub={old.length ? t('agentList.fig.older', { count: old.length, newest: newest ?? '?' }) : newest ? t('agentList.fig.newest', { newest }) : undefined} />
    </StatGrid>
  )
}

/** A group's strip above its agents: its tags as its name, failover state; the name leads to the group's page once there is one. */
function GroupHead({ group: g }: { group: ListGroup }) {
  const { t } = useTranslation()
  const href = g.state ? groupHref(g.id) : null
  return (
    <Group className="fb-agent-group" justify="space-between" gap="xs" wrap="wrap" role="heading" aria-level={3}>
      <Group gap="xs" wrap="wrap" style={{ minWidth: 0 }}>
        <Text fw={600} size="sm">{href ? <Anchor component={Link} to={href} c="inherit">{g.label}</Anchor> : g.label}</Text>
        {g.state && (
          <Tooltip label={t(`agents.ha.help.${g.state}`)} multiline w={300} withArrow>
            <Badge variant="light" color={g.state === 'single' ? 'gray' : STATE_COLOR[g.state]} tt="none" tabIndex={0}>
              {t(`agents.ha.state.${g.state}`)}
            </Badge>
          </Tooltip>
        )}
      </Group>
      <Group gap="sm" wrap="nowrap">
        <Text size="xs" c="dimmed">{t('agentList.agents', { count: g.rows.length })}</Text>
        {href && <Anchor component={Link} to={href} size="xs">{t('agentList.groupPage')}</Anchor>}
      </Group>
    </Group>
  )
}

function AgentTable({ group, head, selected, onSelect, newest }: {
  group: ListGroup; head: boolean; selected: string | null; onSelect: (id: string) => void; newest?: string | null
}) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const num = (n: number, digits = 0) => n.toLocaleString(lang, { maximumFractionDigits: digits })
  const columns: DataColumn<ListRow>[] = [
    { id: 'state', className: 'fb-al-state', header: <VisuallyHidden>{t('agentList.col.state')}</VisuallyHidden>, card: 'inline',
      cell: (r) => <StatusBit tone={TONE_BIT[r.tone]} label={t(`agents.state.${stateKey(r.agent, r.tone)}`)} /> },
    { id: 'agent', className: 'fb-al-agent', header: t('agentList.col.agent'), card: 'inline', wrap: true, cell: (r) => (
      <div style={{ minWidth: 0 }}>
        <Text size="sm" fw={600} style={{ overflowWrap: 'anywhere' }}>{r.agent.name}</Text>
        <Text size="xs" c="dimmed" ff="monospace">
          {r.agent.address ?? '–'}{!r.agent.connected && ` · ${r.agent.last_seen ? ago(r.agent.last_seen, lang) : t('agents.neverSeen')}`}
        </Text>
      </div>
    ) },
    { id: 'role', className: 'fb-al-role', header: t('agentList.col.role'), card: 'label',
      cell: (r) => <Badge variant="light" color={ROLE_COLOR[r.role]} tt="none">{t(`agentList.role.${r.role}`)}</Badge> },
    { id: 'devices', className: 'fb-al-devices', header: t('agentList.col.devices'), numeric: true, card: 'label',
      cell: (r) => (r.devices == null ? '–' : num(r.devices)) },
    { id: 'syslog', className: 'fb-al-syslog', header: t('agentList.col.syslog'), numeric: true, card: 'label', hideOnPhone: true,
      cell: (r) => (r.syslog == null ? '–' : num(r.syslog, r.syslog < 10 ? 1 : 0)) },
    { id: 'load', className: 'fb-al-load', header: t('agentList.col.load'), card: 'label', hideOnPhone: true, cell: (r) => <Load row={r} /> },
    { id: 'version', className: 'fb-al-version', header: t('agentList.col.version'), card: 'label', cell: (r) => (
      <Group gap={4} wrap="nowrap">
        <span>{r.agent.version ?? '–'}</span>
        {r.old && <Badge size="xs" variant="light" color="warn" tt="none" title={newest ? t('agentList.newest', { newest }) : undefined}>{t('agents.outdated')}</Badge>}
      </Group>
    ) },
    { id: 'look', className: 'fb-al-look', header: t('agentList.col.look'), wrap: true, card: 'label', cell: (r) => {
      const first = r.problems[0]
      if (!first) return <Text size="xs" c="dimmed">–</Text>
      return (
        <Text size="xs" c={first.tone} style={{ overflowWrap: 'anywhere' }}>
          {first.text}
          {r.problems.length > 1 && <Text span size="xs" c="dimmed">{' · '}{t('agentList.more', { count: r.problems.length - 1 })}</Text>}
        </Text>
      )
    } },
  ]
  return (
    <DataTable rows={group.rows} columns={columns} rowKey={(r) => r.agent.id} label={t('agentList.groupLabel', { group: group.label })}
      urlState={false} pageSize={0} bare cards head={head} density="compact" minWidth={860}
      selected={selected} onSelect={(id) => onSelect(id)} onRowClick={(r) => onSelect(r.agent.id)}
      rowLabel={(r) => r.agent.name}
      />
  )
}

/** The last hour of work as a small line, with the latest figure in words for screen readers. */
function Load({ row, big }: { row: ListRow; big?: boolean }) {
  const { t, i18n } = useTranslation()
  if (row.load.length < 2) return <Text size="xs" c="dimmed">–</Text>
  const now = row.load[row.load.length - 1]
  const words = t('agentList.loadNow', { n: now.toLocaleString(i18n.language, { maximumFractionDigits: 0 }) })
  return (
    <div className={big ? 'fb-agent-load is-big' : 'fb-agent-load'} role="img" aria-label={words} title={words}>
      <Sparkline points={row.load} min={0} />
    </div>
  )
}

/** One agent beside the list: where it stands, what needs a look and the logins to clear; its own page has the rest. */
function AgentPanel({ row, group, onClose, onPrev, onNext }: {
  row: ListRow; group?: ListGroup; onClose: () => void; onPrev?: () => void; onNext?: () => void
}) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { agent: a, problems } = row
  const list = plugins(a)
  return (
    <SidePanel onClose={onClose} title={a.name} eyebrow={group?.label}
      subtitle={<Group gap={6}><StatusBit tone={TONE_BIT[row.tone]} /><span>{t(`agents.state.${stateKey(a, row.tone)}`)}</span></Group>}
      href={agentHref(a.id)} openLabel={t('agentList.openPage')} onPrev={onPrev} onNext={onNext} padded={false}
      resizable={{ storageKey: 'floorbit.agentPanel.width' }}>
      <PanelSection>
        <SimpleGrid cols={2} spacing="sm" verticalSpacing="xs">
          <PanelField label={t('agentList.col.role')}>{t(`agentList.role.${row.role}`)}</PanelField>
          <PanelField label={t('agentList.address')}><Text span size="sm" ff="monospace">{a.address ?? '–'}</Text></PanelField>
          <PanelField label={t('agentList.col.devices')}>{row.devices == null ? '–' : row.devices.toLocaleString(lang)}</PanelField>
          <PanelField label={t('agents.fact.version')}>
            <Group gap={4} wrap="nowrap">
              <span>{a.version ?? '–'}</span>
              {row.old && <Badge size="xs" variant="light" color="warn" tt="none">{t('agents.outdated')}</Badge>}
            </Group>
          </PanelField>
          <PanelField label={t('agents.fact.link')}>{a.connected ? t(`agents.transport.${a.transport ?? 'elsewhere'}`) : '–'}</PanelField>
          <PanelField label={a.connected ? t('agents.fact.up') : t('agents.fact.seen')}>
            {a.connected ? upText(t, a) : a.last_seen ? ago(a.last_seen, lang) : t('agents.neverSeen')}
          </PanelField>
          <PanelField label={t('agents.fact.calls')}>
            {a.stats?.calls ? t('agents.fact.callsValue', { count: a.stats.calls, n: a.stats.calls.toLocaleString(lang), ms: a.stats.median_ms ?? '–' }) : '–'}
          </PanelField>
          <PanelField label={t('agentList.col.syslog')}>{row.syslog == null ? '–' : row.syslog.toLocaleString(lang, { maximumFractionDigits: 1 })}</PanelField>
        </SimpleGrid>
      </PanelSection>
      {row.load.length > 1 && (
        <PanelSection label={t('agentList.loadTitle')}>
          <Load row={row} big />
        </PanelSection>
      )}
      <PanelSection label={t('agentList.col.look')}>
        {problems.length === 0 ? <Text size="sm" c="dimmed">{t('agentList.nothing')}</Text> : (
          <Stack gap={4}>
            {problems.filter((p) => !p.blocked).slice(0, SHOWN_PROBLEMS).map((p, i) => (
              <Text key={i} size="sm" c={p.tone} style={{ overflowWrap: 'anywhere' }}>{p.text}{p.link && <>{' '}<HintAnchor link={p.link} /></>}</Text>
            ))}
            {problems.filter((p) => !p.blocked).length > SHOWN_PROBLEMS && (
              <Text size="xs" c="dimmed">{t('agentList.more', { count: problems.filter((p) => !p.blocked).length - SHOWN_PROBLEMS })}</Text>
            )}
            <Blocked agentId={a.id} plugins={a.report?.plugins} lang={lang} size="sm" />
          </Stack>
        )}
      </PanelSection>
      {list.length > 0 && (
        <PanelSection label={t('agents.pluginsShort')}>
          <Group gap={6} wrap="wrap" aria-label={t('agents.pluginsShort')}>
            {list.map(([id, p]) => (
              <Badge key={id} variant="light" color={PLUGIN_COLOR[p.status] ?? 'gray'} tt="none"
                title={[t(p.running ? `agents.pluginStatus.${p.status}` : 'agents.pluginNotRunning'), pluginSays(p, t).text].filter(Boolean).join(' · ')}>
                {id}
              </Badge>
            ))}
          </Group>
        </PanelSection>
      )}
    </SidePanel>
  )
}
