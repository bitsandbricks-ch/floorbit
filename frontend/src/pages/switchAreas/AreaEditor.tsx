import { Button, Group, Modal, MultiSelect, Stack, Switch, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { SwitchArea } from '@/api/types'
import type { EntityOption } from '@/components/EntitySelect'
import { RowsSelect } from '@/components/RowsSelect'

/** Pin a switch to blocks, rows or single seats, or leave it out (issue #948). A pin wins over
 *  what was learned and where the switch is drawn. */
export function AreaEditor({ sw, blocks, saving, onClose, onSave }: {
  sw: SwitchArea; blocks: { id: string; label: string }[]; saving: boolean
  onClose: () => void; onSave: (area: SwitchArea['manual']) => void
}) {
  const { t } = useTranslation()
  const [area, setArea] = useState(sw.manual)
  const seats = useQuery({
    queryKey: qk.options('seats', ''),
    queryFn: () => get<{ options: EntityOption[] }>('/api/options/seats'),
    staleTime: 30_000,
  })
  return (
    <Modal opened onClose={onClose} title={t('switchAreas.editTitle', { name: sw.name })}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('switchAreas.editHint')}</Text>
        <Switch label={t('switchAreas.exclude')} description={t('switchAreas.excludeHint')} checked={area.exclude}
          onChange={(e) => setArea({ ...area, exclude: e.currentTarget.checked })} />
        <MultiSelect label={t('switchAreas.blocks')} searchable disabled={area.exclude} value={area.blocks}
          data={blocks.map((b) => ({ value: b.id, label: b.label }))} onChange={(v) => setArea({ ...area, blocks: v })} />
        <RowsSelect label={t('switchAreas.rowsLabel')} disabled={area.exclude} value={area.rows}
          onChange={(v) => setArea({ ...area, rows: v })} />
        <MultiSelect label={t('switchAreas.seatsLabel')} searchable limit={200} disabled={area.exclude} value={area.seats}
          data={(seats.data?.options ?? []).map((o) => o.value)} onChange={(v) => setArea({ ...area, seats: v })} />
        <Group justify="space-between">
          <Button variant="subtle" color="gray" disabled={saving}
            onClick={() => onSave({ blocks: [], rows: [], seats: [], exclude: false })}>{t('switchAreas.clear')}</Button>
          <Group gap="xs">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button loading={saving} onClick={() => onSave(area)}>{t('switchAreas.save')}</Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  )
}
