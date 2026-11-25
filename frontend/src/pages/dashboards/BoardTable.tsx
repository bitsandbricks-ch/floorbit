import { ActionIcon, Anchor, Badge, Group, Menu, Stack, Text, Tooltip, VisuallyHidden } from '@mantine/core'
import { IconArrowRight, IconDeviceTv, IconDots, IconDownload, IconPencil, IconPin, IconPinFilled } from '@tabler/icons-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { type DataColumn, DataTable, FilterBar, useFilters } from '@bitsandbricks/ui'
import { useMe } from '@/api/queries'
import { readBoot, useNavPrefs } from '@/nav/boot'
import { boardHref } from '@/nav/sections'
import { dateTime } from '@/lib/time'
import { paneCount } from './grid'
import { type Board, boardName } from './model'
import { SHOWS, type Show, matches, shows } from './boardFilter'
import { Thumbs } from './Thumbs'
import './BoardTable.css'

/** The dashboards as one table (#897): a preview, what it is, where it shows and when it changed,
 *  a pin for the sidebar. Search and filters stay in the address. */
export function BoardTable({ boards, loading, canEdit, onEdit }: { boards: Board[]; loading: boolean; canEdit: boolean; onEdit: (id: string) => void }) {
  const { t } = useTranslation()
  const [prefs, setPrefs] = useNavPrefs(readBoot())
  const me = useMe().data?.user?.username ?? null
  const filters = useFilters({ show: 'all', tag: '', group: '' })
  const show = (SHOWS.includes(filters.values.show as Show) ? filters.values.show : 'all') as Show
  const isPinned = (id: string) => prefs.favourites.includes(`dashboard:${id}`)
  const pin = (id: string) => {
    const fav = `dashboard:${id}`
    setPrefs({ ...prefs, favourites: isPinned(id) ? prefs.favourites.filter((x) => x !== fav) : [...prefs.favourites, fav] })
  }
  const ctx = { pinned: isPinned, me }
  const tags = useMemo(() => [...new Set(boards.flatMap((b) => b.tags ?? []))].sort(), [boards])
  const groups = useMemo(() => [...new Set(boards.map((b) => b.group).filter((g): g is string => !!g))].sort((a, b) => a.localeCompare(b)), [boards])
  const rows = boards.filter((b) => shows(b, show, ctx) && matches(b, filters.search, boardName(t, b))
    && (!filters.values.tag || (b.tags ?? []).includes(filters.values.tag))
    && (!filters.values.group || b.group === filters.values.group))
  const offered = SHOWS.filter((s) => s === 'all' || s === show || boards.some((b) => shows(b, s, ctx)))

  const columns: DataColumn<Board>[] = [
    { id: 'preview', header: t('dashboardList.preview'), width: 132, hideOnPhone: true,
      cell: (b) => <div className="fb-board-thumb fb-board-row-thumb" aria-hidden="true"><Thumbs sections={b.sections} /></div> },
    { id: 'name', header: t('dashboardList.name'), wrap: true, sort: (b) => boardName(t, b).toLowerCase(),
      text: (b) => boardName(t, b),
      cell: (b) => (
        <Stack gap={4}>
          <Anchor component={Link} to={boardHref(b.id)} fw={600} c="inherit">{boardName(t, b)}</Anchor>
          <Group gap={4}>
            {b.plugin
              ? <Badge size="xs" variant="light" color="trace">{t('dashboards.file.fromPlugin', { plugin: b.plugin_name ?? b.plugin })}</Badge>
              : (b.builtin || b.changed) && <Badge size="xs" variant="light" color="gray">{t('dashboards.builtin')}</Badge>}
            {b.changed && <Badge size="xs" variant="light" color="warn">{t('dashboards.changed')}</Badge>}
            {b.public && <Badge size="xs" variant="light" color="up">{t('dashboards.publicBadge')}</Badge>}
            {(b.tags ?? []).map((tag) => (
              <Badge key={tag} size="xs" variant="default" tt="none" className="fb-board-tag"
                onClick={(e) => { e.preventDefault(); filters.set('tag', tag) }} component="button" type="button"
                aria-label={t('dashboardList.byTag', { tag })}>{tag}</Badge>
            ))}
          </Group>
          <Text size="xs" c="dimmed">
            {t(b.fit ? 'dashboardList.screenLayout' : 'dashboardList.pageLayout')} · {t('dashboards.panes', { count: paneCount(b.sections) })}
          </Text>
        </Stack>
      ) },
    { id: 'group', header: t('dashboardList.group'), hideOnPhone: true, sort: (b) => b.group?.toLowerCase() ?? null,
      cell: (b) => b.group ? <Text size="sm">{b.group}</Text> : <Text size="sm" c="dimmed">–</Text> },
    { id: 'shows', header: t('dashboardList.showsOn'), hideOnPhone: true, text: (b) => showsOn(t, b),
      cell: (b) => <Text size="sm" c={b.public || b.screens ? undefined : 'dimmed'}>{showsOn(t, b)}</Text> },
    { id: 'changed', header: t('dashboardList.changedAt'), hideOnPhone: true, descFirst: true, sort: (b) => b.updated_at ?? 0,
      text: (b) => (b.updated_at ? dateTime(b.updated_at) : ''),
      cell: (b) => <Text size="sm" c="dimmed">{b.updated_at ? `${dateTime(b.updated_at)}${b.by ? ` · ${b.by}` : ''}` : '–'}</Text> },
    { id: 'pin', header: <VisuallyHidden>{t('dashboardList.pin')}</VisuallyHidden>, width: 44, card: 'actions',
      cell: (b) => {
        const on = isPinned(b.id)
        const label = t(on ? 'board.unpin' : 'board.pin')
        return (
          <Tooltip label={label}>
            <ActionIcon variant="subtle" color={on ? 'bit' : 'gray'} aria-pressed={on} aria-label={`${label}: ${boardName(t, b)}`}
              onClick={(e) => { e.stopPropagation(); pin(b.id) }}>
              {on ? <IconPinFilled size={16} /> : <IconPin size={16} />}
            </ActionIcon>
          </Tooltip>
        )
      } },
    { id: 'more', header: <VisuallyHidden>{t('dashboardList.more')}</VisuallyHidden>, width: 44, card: 'actions',
      cell: (b) => (
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" aria-label={t('dashboardList.moreFor', { name: boardName(t, b) })}><IconDots size={16} /></ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item component={Link} to={boardHref(b.id)} leftSection={<IconArrowRight size={16} />}>{t('ui.open')}</Menu.Item>
            {/* The big screen is the second way in, without the app around it. */}
            <Menu.Item component="a" href={`/dashboards/${encodeURIComponent(b.id)}`} leftSection={<IconDeviceTv size={16} />}>{t('board.bigScreen')}</Menu.Item>
            {canEdit && <Menu.Item leftSection={<IconPencil size={16} />} onClick={() => onEdit(b.id)}>{t('dashboards.editOne')}</Menu.Item>}
            <Menu.Item component="a" href={`/api/dashboards/${encodeURIComponent(b.id)}/export`} download leftSection={<IconDownload size={16} />}>{t('dashboards.file.export')}</Menu.Item>
          </Menu.Dropdown>
        </Menu>
      ) },
  ]

  return (
    <Stack gap="sm">
      <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('dashboardList.search')} onClear={filters.clear}
        groups={filters.groups([
          { key: 'show', label: t('dashboardList.show'), options: offered.map((s) => ({
            value: s, label: t(`dashboardList.shows.${s}`), count: boards.filter((b) => shows(b, s, ctx)).length,
          })) },
          { key: 'tag', label: t('dashboardList.tag'), kind: 'select', hidden: tags.length === 0,
            options: [{ value: '', label: t('dashboardList.any') }, ...tags.map((x) => ({ value: x, label: x }))] },
          { key: 'group', label: t('dashboardList.group'), kind: 'select', hidden: groups.length === 0,
            options: [{ value: '', label: t('dashboardList.any') }, ...groups.map((x) => ({ value: x, label: x }))] },
        ])} />
      <DataTable rows={rows} columns={columns} rowKey={(b) => b.id} label={t('dashboards.title')} loading={loading} cards
        defaultSort={{ id: 'name' }} count={(n) => t('dashboardList.count', { count: n })}
        empty={<Text c="dimmed" py="md">{boards.length ? t('dashboardList.noMatch') : t('dashboards.empty')}</Text>} />
    </Stack>
  )
}

/** Where a dashboard shows: open to anyone, on screen accounts, or only inside the app. */
function showsOn(t: (k: string, o?: Record<string, unknown>) => string, b: Board): string {
  const parts = [b.public ? t('dashboardList.public') : '', b.screens ? t('dashboardList.screens', { count: b.screens }) : ''].filter(Boolean)
  return parts.length ? parts.join(' · ') : t('dashboardList.inApp')
}
