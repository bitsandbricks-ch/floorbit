import { Button, Input, SegmentedControl, Stack, Text } from '@mantine/core'
import { IconArmchair } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { autoChairs, withCables } from './autoChairs'
import { type BlockRow, ROW_CABLES, type RowCables } from './rows'

/** Where a row's seat cables plug in (floorbit/cable_lanes.py): Auto, behind the table, or where
 *  the player sits. ``value`` null: the rows differ, nothing is picked. */
export function CablesConnect({ value, onChange, all = false }: { value: RowCables | null; onChange: (v: RowCables) => void; all?: boolean }) {
  const { t } = useTranslation()
  return (
    <Input.Wrapper label={t(all ? 'seatCables.connectAll' : 'seatCables.connect')} description={t('seatCables.connectHint')}>
      <SegmentedControl fullWidth size="xs" value={value ?? ''} onChange={(v) => onChange(v as RowCables)}
        data={ROW_CABLES.map((v) => ({ value: v, label: t(`seatCables.modes.${v || 'auto'}`) }))} />
    </Input.Wrapper>
  )
}

/** The Block tab's chairs and cables for all rows at once (Mike, issue #1342). */
export function BlockCableFields({ rows, onSave }: { rows: BlockRow[]; onSave: (rows: BlockRow[]) => void }) {
  const { t } = useTranslation()
  const modes = new Set(rows.filter((r) => r.shape === 'line').map((r) => r.cables ?? ''))
  if (!modes.size) return null
  return (
    <Stack gap="xs">
      <div>
        <Button size="xs" variant="default" leftSection={<IconArmchair size={14} />} onClick={() => onSave(autoChairs(rows))}>
          {t('seatCables.autoChairs')}
        </Button>
        <Text size="xs" c="dimmed" mt={4}>{t('seatCables.autoChairsHint')}</Text>
      </div>
      <CablesConnect all value={modes.size === 1 ? [...modes][0] : null} onChange={(v) => onSave(withCables(rows, v))} />
    </Stack>
  )
}
