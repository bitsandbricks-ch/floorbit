import { ActionIcon, Badge, Group, ScrollArea, Stack, Text, TextInput, Tooltip, UnstyledButton } from '@mantine/core'
import { IconChevronDown, IconChevronRight, IconSearch, IconUnlink } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanGroup, SeatViewData } from '@/api/types'
import { useCustomIcons } from '../../inventory/scope'
import { type ItemRef, allItems, refKey, sameRef } from './geometry'

const ORDER: Record<string, number> = { block: 0, switch: 1, panel: 2, board: 3, text: 4, icon: 5, zone: 6, wall: 7 }

/** Every item on this hall's plan, the groups first, then the rest by kind. Click picks an item or
 *  a whole group (Shift adds to the selection), double-click also zooms to it; a group can be
 *  renamed or taken apart here. */
export function ItemList({ data, groups, selected, onSelect, onRename, onUngroup, onFrame }: {
  data: SeatViewData
  groups: PlanGroup[]
  selected: ItemRef[]
  onSelect: (refs: ItemRef[], add: boolean) => void
  onRename: (group: PlanGroup, name: string) => void
  onUngroup: (group: PlanGroup) => void
  onFrame?: (refs: ItemRef[]) => void
}) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const items = allItems(data)
  const exists = (r: ItemRef) => items.some((x) => sameRef(x, r))
  const live = groups.map((g) => ({ ...g, members: g.members.filter(exists) })).filter((g) => g.members.length >= 2)
  const inGroup = (r: ItemRef) => live.some((g) => g.members.some((m) => sameRef(m, r)))
  const uploaded = useCustomIcons().data?.icons
  const name = (r: ItemRef) => itemName(t, data, r, uploaded)
  const kindOf = (r: ItemRef) => (r.kind === 'mark' ? data.drawing?.marks?.find((m) => m.id === r.id)?.kind ?? 'text' : r.kind)
  const match = (r: ItemRef) => !q.trim() || name(r).toLowerCase().includes(q.trim().toLowerCase())
  const loose = items.filter((r) => !inGroup(r) && match(r))
    .sort((a, b) => ORDER[kindOf(a)] - ORDER[kindOf(b)] || name(a).localeCompare(name(b), undefined, { numeric: true }))
  const shownGroups = live.filter((g) => !q.trim() || g.name.toLowerCase().includes(q.trim().toLowerCase()) || g.members.some(match))
  const isSel = (r: ItemRef) => selected.some((s) => sameRef(s, r))
  const toggle = (id: string) => setOpen((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n })

  const row = (r: ItemRef, indent = false) => (
    <UnstyledButton key={refKey(r)} className="fb-item-row" data-selected={isSel(r) || undefined} pl={indent ? 28 : 8}
      onClick={(e) => onSelect([r], e.shiftKey || e.metaKey || e.ctrlKey)} onDoubleClick={() => onFrame?.([r])}>
      <Text size="sm" truncate>{name(r)}</Text>
    </UnstyledButton>
  )

  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Text size="sm" fw={600}>{t('plan.edit.items.title')}</Text>
        <Text size="xs" c="dimmed">{t('plan.edit.items.count', { count: items.length })}</Text>
      </Group>
      <TextInput size="xs" placeholder={t('plan.edit.items.search')} aria-label={t('plan.edit.items.search')} leftSection={<IconSearch size={14} />}
        value={q} onChange={(e) => setQ(e.currentTarget.value)} />
      <ScrollArea.Autosize mah={300} type="auto" offsetScrollbars>
        <Stack gap={1}>
          {shownGroups.map((g) => {
            const all = g.members.every(isSel)
            const unfolded = open.has(g.id) || !!q.trim()
            return (
              <div key={g.id}>
                <Group gap={2} wrap="nowrap" className="fb-item-row" data-selected={all || undefined}>
                  <ActionIcon size="sm" variant="subtle" color="gray" aria-label={t(unfolded ? 'plan.edit.items.fold' : 'plan.edit.items.unfold')} onClick={() => toggle(g.id)}>
                    {unfolded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                  </ActionIcon>
                  <GroupName group={g} onSelect={(add) => onSelect(g.members, add)} onRename={(n) => onRename(g, n)} />
                  <Badge size="xs" variant="light" color="gray">{g.members.length}</Badge>
                  <Tooltip label={t('plan.edit.menu.ungroup')}>
                    <ActionIcon size="sm" variant="subtle" color="gray" aria-label={t('plan.edit.menu.ungroup')} onClick={() => onUngroup(g)}><IconUnlink size={14} /></ActionIcon>
                  </Tooltip>
                </Group>
                {unfolded && g.members.filter((m) => !q.trim() || match(m) || g.name.toLowerCase().includes(q.trim().toLowerCase())).map((m) => row(m, true))}
              </div>
            )
          })}
          {loose.map((r) => row(r))}
          {!shownGroups.length && !loose.length && <Text size="xs" c="dimmed" p={8}>{t(items.length ? 'plan.edit.items.none' : 'plan.edit.items.empty')}</Text>}
        </Stack>
      </ScrollArea.Autosize>
      {!live.length && items.length > 1 && <Text size="xs" c="dimmed">{t('plan.edit.items.groupHelp')}</Text>}
    </Stack>
  )
}

/** A group's name: click picks the group, double-click renames it (Enter saves, Escape stops). */
function GroupName({ group, onSelect, onRename }: { group: PlanGroup; onSelect: (add: boolean) => void; onRename: (name: string) => void }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<string | null>(null)
  if (editing != null) {
    const done = () => { const n = editing.trim(); setEditing(null); if (n && n !== group.name) onRename(n) }
    return (
      <TextInput size="xs" style={{ flex: 1 }} autoFocus value={editing} maxLength={40} aria-label={t('plan.edit.items.rename')}
        onChange={(e) => setEditing(e.currentTarget.value)} onBlur={done}
        onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') done(); if (e.key === 'Escape') setEditing(null) }} />
    )
  }
  return (
    <Tooltip label={t('plan.edit.items.renameHelp')} openDelay={600}>
      <UnstyledButton style={{ flex: 1, minWidth: 0 }} onClick={(e) => onSelect(e.shiftKey || e.metaKey || e.ctrlKey)} onDoubleClick={() => setEditing(group.name)}>
        <Text size="sm" fw={500} truncate>{group.name || t('plan.edit.groups.unnamed')}</Text>
      </UnstyledButton>
    </Tooltip>
  )
}

function itemName(t: (k: string, o?: Record<string, unknown>) => string, data: SeatViewData, r: ItemRef, uploaded?: { id: string; name: string }[]): string {
  if (r.kind === 'block') return t('plan.edit.kind.block', { name: data.drawing?.shapes.find((s) => s.id === r.id)?.name || '—' })
  if (r.kind === 'switch') return t('plan.edit.kind.switch', { name: data.switches.find((w) => w.id === r.id)?.name ?? '' })
  if (r.kind === 'panel') return t('plan.edit.kind.panel', { name: r.id })
  if (r.kind === 'board') return t('plan.edit.kind.board', { name: data.boards?.find((b) => b.id === r.id)?.name ?? '' })
  if (r.kind === 'cable') return t('plan.edit.kind.cable')
  const m = data.drawing?.marks?.find((x) => x.id === r.id)
  const what = t(`plan.edit.kind.${m?.kind ?? 'text'}`)
  const detail = m?.kind === 'text' ? m.text : m?.kind === 'zone' ? m.label : m?.kind === 'icon' ? iconName(t, m.icon ?? '', uploaded) : ''
  return detail ? `${what}: ${detail}` : what
}

/** An uploaded icon by its name in the library, a built-in one by its translated name. */
function iconName(t: (k: string, o?: Record<string, unknown>) => string, icon: string, uploaded?: { id: string; name: string }[]) {
  return uploaded?.find((u) => u.id === icon)?.name ?? t(`plan.edit.icons.${icon}`, { defaultValue: icon.replace(/[-_]/g, ' ') })
}
