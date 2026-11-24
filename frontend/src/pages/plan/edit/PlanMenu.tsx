import { Anchor, Badge, Button, Group, Menu, Modal, Paper, Stack, Text } from '@mantine/core'
import { IconBookmarks, IconBuildingWarehouse, IconChevronDown, IconDeviceFloppy, IconHistoryToggle, IconTemplate } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { LayoutTemplate, SeatViewData } from '@/api/types'
import { ApplyDialog, SaveDialog } from '../../templates/Dialogs'
import { HallsDialog } from './HallsDialog'
import { type PlanPreset, PresetsDialog } from './Presets'
import { VersionsDialog } from './VersionsDialog'
import { toastDone } from '@bitsandbricks/ui'

/** What the editor's Plan menu opens (issue #1210). */
export type PlanDialog = 'save' | 'start' | 'presets' | 'versions' | 'halls'

/** The editor's Plan ▾ menu in the top bar: the plan as a whole, next to the tools for its parts. */
export function PlanMenu({ onOpen }: { onOpen: (d: PlanDialog) => void }) {
  const { t } = useTranslation()
  return (
    <Menu position="bottom-end" withinPortal width={250}>
      <Menu.Target>
        <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} aria-hidden="true" />}>{t('planMenu.button')}</Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconDeviceFloppy size={14} />} onClick={() => onOpen('save')}>{t('planMenu.save')}</Menu.Item>
        <Menu.Item leftSection={<IconTemplate size={14} />} onClick={() => onOpen('start')}>{t('planMenu.start')}</Menu.Item>
        <Menu.Item leftSection={<IconBookmarks size={14} />} onClick={() => onOpen('presets')}>{t('presets.menuPlace')}</Menu.Item>
        <Menu.Divider />
        <Menu.Item leftSection={<IconHistoryToggle size={14} />} onClick={() => onOpen('versions')}>{t('planMenu.versions')}</Menu.Item>
        <Menu.Item leftSection={<IconBuildingWarehouse size={14} />} onClick={() => onOpen('halls')}>{t('planMenu.halls')}</Menu.Item>
        <Menu.Divider />
        <Menu.Item component="a" href="/templates">{t('planMenu.library')}</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}

/** The templates to start from; picking one asks the version and where it goes. */
function StartDialog({ data, onClose, onApplied }: { data: SeatViewData; onClose: () => void; onApplied: () => Promise<unknown> }) {
  const { t } = useTranslation()
  const list = useQuery({ queryKey: qk.templates, queryFn: () => get<{ templates: LayoutTemplate[] }>('/api/templates').then((d) => d.templates) })
  const [picked, setPicked] = useState<LayoutTemplate | null>(null)
  if (picked) {
    return (
      <ApplyDialog template={picked} halls={data.halls} hall={data.hall} onClose={() => setPicked(null)}
        onDone={(r) => { toastDone(t('templates.applied', { ...r })); onClose(); void onApplied() }} />
    )
  }
  const templates = [...(list.data ?? [])].sort((a, b) => b.updated.localeCompare(a.updated))
  return (
    <Modal opened onClose={onClose} title={t('planMenu.startTitle')} size="lg">
      <Stack gap="sm">
        {!templates.length && !list.isPending && <Text size="sm" c="dimmed">{t('planMenu.noTemplates')}</Text>}
        <Stack gap="xs" role="list" aria-label={t('planMenu.templates')}>
          {templates.map((tpl) => {
            const last = tpl.versions[tpl.versions.length - 1]
            return (
              <Paper key={tpl.id} withBorder p="sm" role="listitem">
                <Group justify="space-between" wrap="nowrap" gap="sm">
                  <Stack gap={4} style={{ minWidth: 0 }}>
                    <Text fw={600} truncate>{tpl.name}</Text>
                    {tpl.description && <Text size="xs" c="dimmed" lineClamp={2}>{tpl.description}</Text>}
                    <Group gap={6}>
                      <Badge size="sm" variant="light" color="gray">{t('templates.halls', { count: last.halls })}</Badge>
                      <Badge size="sm" variant="light" color="gray">{t('templates.blocks', { count: last.seat_blocks })}</Badge>
                      <Badge size="sm" variant="light" color="gray">{t('templates.switches', { count: last.switches })}</Badge>
                    </Group>
                  </Stack>
                  <Button size="xs" variant="default" onClick={() => setPicked(tpl)} aria-label={t('planMenu.use', { name: tpl.name })}>{t('templates.apply')}</Button>
                </Group>
              </Paper>
            )
          })}
        </Stack>
        <Text size="xs" c="dimmed">{t('planMenu.startHelp')} <Anchor href="/templates" size="xs">{t('planMenu.library')}</Anchor></Text>
      </Stack>
    </Modal>
  )
}

/** The dialogs the Plan menu opens, inside the editor so a restored plan also clears its undo. */
export function PlanDialogs({ open, data, onClose, onHall, onChanged, onReplaced, onPlace }: {
  open: PlanDialog | null
  data: SeatViewData
  onClose: () => void
  onHall: (id: string) => void
  onChanged: () => Promise<unknown>
  /** The plan was replaced by a template or a version: what could be undone is gone. */
  onReplaced: () => Promise<unknown>
  /** Puts a preset's items on the plan, like a paste. */
  onPlace: (p: PlanPreset) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const hallName = data.halls.find((h) => h.id === data.hall)?.name ?? data.hall
  return (
    <>
      {open === 'save' && (
        <SaveDialog halls={data.halls} hall={data.halls.length > 1 ? data.hall : ''} onClose={onClose}
          onDone={(tpl) => { toastDone(t('templates.saved', { name: tpl.name })); void qc.invalidateQueries({ queryKey: qk.templates }); onClose() }} />
      )}
      {open === 'start' && <StartDialog data={data} onClose={onClose} onApplied={onReplaced} />}
      <PresetsDialog opened={open === 'presets'} onClose={onClose} onPlace={onPlace} />
      <VersionsDialog opened={open === 'versions'} hall={data.hall} hallName={hallName} onClose={onClose} onRestored={onReplaced} />
      <HallsDialog opened={open === 'halls'} current={data.hall} onClose={onClose} onOpen={onHall} onChanged={onChanged} />
    </>
  )
}

/** In the panel of an empty hall: start from a template instead of drawing it all again. */
export function EmptyHall({ onStart }: { onStart: () => void }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder p="sm" radius="md">
      <Stack gap={6} align="flex-start">
        <Text fw={600} size="sm">{t('planMenu.emptyTitle')}</Text>
        <Text size="xs" c="dimmed">{t('planMenu.emptyHelp')}</Text>
        <Button size="xs" variant="light" leftSection={<IconTemplate size={14} />} onClick={onStart}>{t('planMenu.start')}</Button>
      </Stack>
    </Paper>
  )
}
