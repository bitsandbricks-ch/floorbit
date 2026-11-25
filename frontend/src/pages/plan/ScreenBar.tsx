import { Group, Text } from '@mantine/core'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanBlock } from '@/api/types'
import { clock } from '@/lib/time'
import { troubleBlocks } from './screen'

/** The big screen's right-hand corner: the time, problems in the other halls, and which blocks
 *  have problems, so the crew sees where to go without walking up to the screen. */
export function ScreenBar({ blocks, elsewhere }: { blocks: PlanBlock[]; elsewhere: number }) {
  const { t, i18n } = useTranslation()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  const { shown, more } = troubleBlocks(blocks)
  return (
    <div className="fb-screen-bar">
      <Text className="fb-screen-clock" fw={800}>{clock(now, i18n.language)}</Text>
      {shown.length > 0 && (
        <Group gap={6} justify="flex-end" className="fb-screen-blocks" aria-label={t('plan.screen.blocks')}>
          {shown.map((b) => (
            <span key={b.id ?? b.name} className="fb-screen-block">{t('plan.screen.block', { name: b.label || b.name, count: b.problems })}</span>
          ))}
          {more > 0 && <span className="fb-screen-block more">{t('plan.screen.more', { count: more })}</span>}
        </Group>
      )}
      {elsewhere > 0 && <Text className="fb-screen-elsewhere" c="down" fw={600}>{t('plan.elsewhere', { count: elsewhere })}</Text>}
    </div>
  )
}
