import { Button, Text } from '@mantine/core'
import { IconArrowLeft } from '@tabler/icons-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

/** The bar above a large pane: back to the dashboard (Esc does the same). On a wall (``backAfter``)
 *  it goes back by itself, so a screen nobody watches returns to the whole dashboard. */
export function LargeBar({ onBack, backAfter }: { onBack: () => void; backAfter?: number }) {
  const { t } = useTranslation()
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape' && !e.defaultPrevented) onBack() }
    window.addEventListener('keydown', key)
    const timer = backAfter ? window.setTimeout(onBack, backAfter * 1000) : undefined
    return () => { window.removeEventListener('keydown', key); window.clearTimeout(timer) }
  }, [onBack, backAfter])
  return (
    <div className="fb-grid-large-bar">
      <Button size="xs" variant="default" leftSection={<IconArrowLeft size={14} aria-hidden="true" />} onClick={onBack}>
        {t('dashboards.large.back')}
      </Button>
      <Text size="xs" c="dimmed">{backAfter ? t('dashboards.large.backAfter', { seconds: backAfter }) : t('dashboards.large.esc')}</Text>
    </div>
  )
}
