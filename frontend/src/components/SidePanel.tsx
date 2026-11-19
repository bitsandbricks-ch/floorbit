import { Button, Drawer, Group, Stack, Text } from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

/** A quick look from the right: a row on a list opens it, the list stays where it was, and
 *  "Open" leads on to the thing's own page. One look for every page (devices, seats, incidents,
 *  notifications). ``href`` adds the "Open" button; ``actions`` go next to it. */
export function SidePanel({ opened, onClose, title, kicker, href, openLabel, actions, size = 440, children }: {
  opened: boolean
  onClose: () => void
  title: ReactNode
  /** One small line above the title (a type, a place). */
  kicker?: ReactNode
  href?: string
  openLabel?: string
  actions?: ReactNode
  size?: number | string
  children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <Drawer
      opened={opened} onClose={onClose} position="right" size={size} padding={0}
      classNames={{ content: 'fb-side', header: 'fb-side-head', body: 'fb-side-body' }}
      closeButtonProps={{ 'aria-label': t('common.close') }}
      title={(
        <Stack gap={2}>
          {kicker && <Text size="xs" c="dimmed">{kicker}</Text>}
          <Text fw={650} size="lg" lh={1.25}>{title}</Text>
        </Stack>
      )}
    >
      {(href || actions) && (
        <Group gap="xs" className="fb-side-actions">
          {href && (
            <Button component={Link} to={href} size="xs" rightSection={<IconArrowRight size={14} aria-hidden="true" />} onClick={onClose}>
              {openLabel ?? t('ui.open')}
            </Button>
          )}
          {actions}
        </Group>
      )}
      <div className="fb-side-content">{children}</div>
    </Drawer>
  )
}
