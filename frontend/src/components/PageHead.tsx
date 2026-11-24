import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Box, Group, Stack, Text, Title } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useInPanel } from './panel'
import { useTopbarSlot } from './topbarSlot'

// From Hubra (by Mike): packages/ui/src/layout.tsx, tightened for the grouped shell.
// On a computer the top bar is the page's one bar (issue #932): its breadcrumb ends in the page's
// title and the buttons sit on its right, so the page has no title row of its own; only the
// sentence about the page (``kicker`` or ``desc``) stays, small, at the top. Phones keep the
// title here, since their bar shows the brand.
export function PageHead({ title, kicker, desc, actions, icon }: {
  title: ReactNode; kicker?: ReactNode; desc?: ReactNode; actions?: ReactNode; icon?: ReactNode
}) {
  // Inside another page's tab the outer page has the h2: this one heads a section.
  const inPanel = useInPanel()
  const wide = useMediaQuery('(min-width: 48em)', false, { getInitialValueInEffect: false })
  const slot = useTopbarSlot()
  const inBar = wide && !inPanel && !!slot
  if (inBar) {
    const about = kicker ?? desc
    return (
      <>
        <Title order={2} className="fb-sr-only">{title}</Title>
        {about && <Text size="sm" c="dimmed" maw={720} mb={16} className="fb-pagehead-about">{about}</Text>}
        {actions && createPortal(<Group gap="xs" wrap="nowrap" align="center">{actions}</Group>, slot)}
      </>
    )
  }
  return (
    <Box mb={inPanel ? 14 : 20} className="fb-pagehead">
      <Group justify="space-between" align="flex-end" gap={16} wrap="wrap">
        <Group gap={14} align="center" wrap="nowrap" style={{ minWidth: 0, flex: '1 1 320px' }}>
          {icon && <span className="fb-pagehead-icon" aria-hidden="true">{icon}</span>}
          <Stack gap={4} style={{ minWidth: 0 }}>
            {kicker && <Text size="sm" c="dimmed" className="fb-pagehead-kicker">{kicker}</Text>}
            <Title order={inPanel ? 3 : 2} fz={inPanel ? 'lg' : undefined} style={{ margin: 0, overflowWrap: 'anywhere' }}>
              {title}
            </Title>
            {desc && (
              <Text size="sm" c="dimmed" maw={720}>
                {desc}
              </Text>
            )}
          </Stack>
        </Group>
        {actions && (
          // Phones: one row that scrolls sideways, so the page starts on screen (styles/shell.css).
          <Group gap="xs" wrap="wrap" align="center" className="fb-pagehead-actions">
            {actions}
          </Group>
        )}
      </Group>
    </Box>
  )
}
