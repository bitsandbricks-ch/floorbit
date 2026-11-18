import { ActionIcon, Badge, Button, Group, Paper, Stack, Text, UnstyledButton } from '@mantine/core'
import { IconFolder, IconFolders, IconPencil, IconPlus, IconTag } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { InventoryOverview } from '@/api/types'
import { DeviceIcon } from './icons'
import { groupTree } from './scope'
import type { ScopeTarget } from './GroupPanel'

export type GroupFilter = null | 'none' | string

function Row({ active, depth = 0, icon, label, count, onSelect, onEdit, editLabel }: {
  active: boolean; depth?: number; icon: React.ReactNode; label: string; count?: number
  onSelect: () => void; onEdit?: () => void; editLabel?: string
}) {
  return (
    <Group gap={4} wrap="nowrap" pl={depth * 14} className={active ? 'fb-tree-row fb-tree-row-active' : 'fb-tree-row'}
      style={{ borderRadius: 6 }}>
      <UnstyledButton onClick={onSelect} aria-pressed={active} style={{ flex: 1, minWidth: 0, padding: '4px 6px' }}>
        <Group gap={6} wrap="nowrap">
          {icon}
          <Text size="sm" fw={active ? 600 : 400} truncate>{label}</Text>
          {count !== undefined && <Text size="xs" c="dimmed" ml="auto">{count}</Text>}
        </Group>
      </UnstyledButton>
      {onEdit && (
        <ActionIcon size="sm" variant="subtle" color="gray" aria-label={editLabel} onClick={onEdit}>
          <IconPencil size={14} />
        </ActionIcon>
      )}
    </Group>
  )
}

/** Groups as a tree and the tags, beside the device list: pick one to filter, the pencil to edit. */
export function GroupTree({ overview, total, group, tags, canEdit, onGroup, onTags, onEdit }: {
  overview: InventoryOverview; total: number; group: GroupFilter; tags: string[]; canEdit: boolean
  onGroup: (g: GroupFilter) => void; onTags: (t: string[]) => void; onEdit: (target: ScopeTarget) => void
}) {
  const { t } = useTranslation()
  return (
    <Stack gap="md">
      <Paper withBorder radius="lg" p="xs">
        <Group justify="space-between" px={6} mb={4}>
          <Text size="xs" fw={650} c="dimmed" tt="uppercase">{t('inventory.groups.title')}</Text>
          {canEdit && (
            <ActionIcon size="sm" variant="subtle" aria-label={t('inventory.groups.new')} onClick={() => onEdit({ kind: 'group', item: null })}>
              <IconPlus size={14} />
            </ActionIcon>
          )}
        </Group>
        <Row active={group === null} icon={<IconFolders size={16} />} label={t('inventory.groups.all')} count={total}
          onSelect={() => onGroup(null)} onEdit={() => onEdit({ kind: 'defaults' })} editLabel={t('inventory.groups.editDefaults')} />
        {groupTree(overview.groups).map(({ group: g, depth }) => (
          <Row key={g.id} active={group === g.id} depth={depth + 1}
            icon={g.icon ? <DeviceIcon icon={g.icon} color={g.color} size={18} /> : <IconFolder size={16} color={g.color || undefined} />}
            label={g.name} count={g.devices} onSelect={() => onGroup(g.id)}
            onEdit={() => onEdit({ kind: 'group', item: g })} editLabel={t('inventory.groups.edit', { name: g.name })} />
        ))}
        {overview.groups.length > 0 && (
          <Row active={group === 'none'} depth={1} icon={<IconFolder size={16} opacity={0.4} />} label={t('inventory.groups.none')}
            count={overview.ungrouped} onSelect={() => onGroup('none')} />
        )}
        {overview.groups.length === 0 && canEdit && (
          <Button size="xs" variant="subtle" fullWidth mt={4} onClick={() => onEdit({ kind: 'group', item: null })}>{t('inventory.groups.first')}</Button>
        )}
      </Paper>
      <Paper withBorder radius="lg" p="xs">
        <Group justify="space-between" px={6} mb={6}>
          <Text size="xs" fw={650} c="dimmed" tt="uppercase">{t('inventory.tags.title')}</Text>
          {canEdit && (
            <ActionIcon size="sm" variant="subtle" aria-label={t('inventory.tags.new')} onClick={() => onEdit({ kind: 'tag', item: null })}>
              <IconPlus size={14} />
            </ActionIcon>
          )}
        </Group>
        {overview.tags.length === 0 ? (
          <Text size="xs" c="dimmed" px={6}>{t('inventory.tags.noneYet')}</Text>
        ) : (
          <Group gap={6} px={4}>
            {[...overview.tags].sort((a, b) => a.name.localeCompare(b.name)).map((tag) => {
              const on = tags.includes(tag.id)
              return (
                <Group key={tag.id} gap={0} wrap="nowrap">
                  <Badge component="button" type="button" tt="none" variant={on ? 'filled' : 'light'} color={tag.color || 'gray'}
                    leftSection={<IconTag size={11} />} style={{ cursor: 'pointer' }} aria-pressed={on}
                    onClick={() => onTags(on ? tags.filter((x) => x !== tag.id) : [...tags, tag.id])}>
                    {tag.name} · {tag.used}
                  </Badge>
                  {canEdit && (
                    <ActionIcon size="xs" variant="subtle" color="gray" aria-label={t('inventory.tags.edit', { name: tag.name })}
                      onClick={() => onEdit({ kind: 'tag', item: tag })}>
                      <IconPencil size={11} />
                    </ActionIcon>
                  )}
                </Group>
              )
            })}
          </Group>
        )}
      </Paper>
    </Stack>
  )
}
