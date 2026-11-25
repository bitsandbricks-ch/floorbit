import { Button, Text } from '@mantine/core'
import { IconArrowsJoin, IconArrowsSplit } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

/** In the selection's panel when two or more seat blocks (and nothing else) are picked. */
export function MergeBlocks({ count, disabled, onMerge }: { count: number; disabled?: boolean; onMerge: () => void }) {
  const { t } = useTranslation()
  return (
    <div>
      <Button variant="default" fullWidth leftSection={<IconArrowsJoin size={16} />} disabled={disabled} onClick={onMerge}>
        {t('blockJoin.merge', { count })}
      </Button>
      <Text size="xs" c="dimmed" mt={4}>{t('blockJoin.mergeHint')}</Text>
    </div>
  )
}

/** Under a block's rows: splits the block above the picked row (not the first). */
export function SplitBlock({ index, name, freely, onSplit }: { index: number; name: string; freely: boolean; onSplit: () => void }) {
  const { t } = useTranslation()
  if (index <= 0) return null
  return (
    <div>
      <Button variant="default" size="xs" leftSection={<IconArrowsSplit size={14} />} disabled={freely} onClick={onSplit}>
        {t('blockJoin.split', { name })}
      </Button>
      <Text size="xs" c="dimmed" mt={4}>{t(freely ? 'blockJoin.splitFreely' : 'blockJoin.splitHint', { name })}</Text>
    </div>
  )
}
