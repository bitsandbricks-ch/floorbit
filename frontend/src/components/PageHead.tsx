import type { ReactNode } from 'react'
import { Box, Group, Stack, Text, Title } from '@mantine/core'

// From Hubra (by Mike): packages/ui/src/layout.tsx, tightened for the grouped shell: a small line
// above the title says what the page is about, the title, and at most two buttons on the right.
// ``desc`` is for the few pages that still need a sentence; prefer ``kicker``.
export function PageHead({ title, kicker, desc, actions, icon }: {
  title: ReactNode; kicker?: ReactNode; desc?: ReactNode; actions?: ReactNode; icon?: ReactNode
}) {
  return (
    <Box mb={20} className="fb-pagehead">
      <Group justify="space-between" align="flex-end" gap={16} wrap="wrap">
        <Group gap={14} align="center" wrap="nowrap" style={{ minWidth: 0, flex: '1 1 320px' }}>
          {icon && <span className="fb-pagehead-icon" aria-hidden="true">{icon}</span>}
          <Stack gap={4} style={{ minWidth: 0 }}>
            {kicker && <Text size="sm" c="dimmed" className="fb-pagehead-kicker">{kicker}</Text>}
            <Title order={2} style={{ margin: 0, overflowWrap: 'anywhere' }}>
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
          // Phones: one row that scrolls sideways, so the page starts on screen (app.css).
          <Group gap="xs" wrap="wrap" align="center" className="fb-pagehead-actions">
            {actions}
          </Group>
        )}
      </Group>
    </Box>
  )
}
